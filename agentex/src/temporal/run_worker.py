"""
Temporal worker entry point for health check workflows.

Each worker process handles one task queue for clean separation and scaling.
"""

import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from src.adapters.temporal.client_factory import TemporalClientFactory
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
    httpx_client,
    startup_global_dependencies,
)
from src.config.environment_variables import EnvironmentVariables
from src.domain.repositories.agent_repository import AgentRepository
from src.temporal.activities.healthcheck_activities import HealthCheckActivities
from src.temporal.activities.retention_cleanup_activities import (
    RetentionCleanupActivities,
)
from src.temporal.task_retention_factory import build_task_retention_use_case
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow
from src.temporal.workflows.retention_cleanup_workflow import (
    RetentionCleanupSweepWorkflow,
    RetentionCleanupTaskWorkflow,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Task queue name for agentex server operations
AGENTEX_SERVER_TASK_QUEUE = "agentex-server"


OTLP_METRICS_DEFAULT_PORT = 4317


def build_metrics_url(host_url: str | None) -> str | None:
    """Build the OTLP metrics endpoint URL from a ``host`` or ``host:port`` value.

    Accepts a bare hostname/IPv4, an IPv6 literal (bracketed or not), or any of
    those with an explicit ``:port`` suffix. Per RFC 3986 only IPv6 literals are
    wrapped in brackets, and the default OTLP gRPC port is appended only when the
    value does not already carry one. Returns None when no host is configured.
    """
    if not host_url:
        return None

    host = host_url.strip()
    port: str | None = None

    if host.startswith("["):
        bracket_end = host.find("]")
        if bracket_end != -1:
            rest = host[bracket_end + 1 :]
            port = rest[1:] if rest.startswith(":") else None
            host = host[1:bracket_end]
    elif host.count(":") == 1:
        host, port = host.split(":", 1)

    bracketed = f"[{host}]" if ":" in host else host
    return f"http://{bracketed}:{port or OTLP_METRICS_DEFAULT_PORT}"


# Global worker instance
health_check_worker: Worker | None = None


async def run_worker(
    task_queue: str = AGENTEX_SERVER_TASK_QUEUE,
    dependency_overrides: dict | None = None,
    workflows: list | None = None,
    activities: list | None = None,
    max_workers: int = 10,
    max_concurrent_activities: int = 50,
) -> None:
    """
    Run the Temporal worker for specified workflows and activities.

    Args:
        task_queue: The task queue to process (default: agentex-server)
        dependency_overrides: Optional dependency overrides for testing
        workflows: List of workflow classes to register
        activities: List of activity functions to register
        max_workers: Maximum number of activity worker threads
        max_concurrent_activities: Maximum concurrent activities

    Raises:
        TemporalError: If worker creation or execution fails
    """
    global health_check_worker

    try:
        # Initialize global dependencies
        await startup_global_dependencies()
        # Get environment variables
        environment_variables = EnvironmentVariables.refresh()

        logger.info(f"Starting Health Check worker for task queue: {task_queue}")
        logger.info(f"Temporal address: {environment_variables.TEMPORAL_ADDRESS}")

        # Check if Temporal is configured
        if not TemporalClientFactory.is_temporal_configured(environment_variables):
            logger.warning("Temporal is not configured, skipping worker creation")
            raise ValueError("Temporal is not properly configured")

        # Check for metrics configuration
        host_url = os.environ.get("DD_AGENT_HOST")
        metrics_url = build_metrics_url(host_url)
        if metrics_url:
            logger.info(f"Configuring worker with metrics URL: {metrics_url}")

        # Create Temporal client
        client = await TemporalClientFactory.create_client_from_env(
            environment_variables=environment_variables,
            metrics_url=metrics_url,
        )

        # Create the worker directly (no manager needed)
        health_check_worker = Worker(
            client,
            task_queue=task_queue,
            activity_executor=ThreadPoolExecutor(max_workers=max_workers),
            workflows=workflows or [],
            activities=activities or [],
            workflow_runner=UnsandboxedWorkflowRunner(),
            max_concurrent_activities=max_concurrent_activities,
            build_id=str(uuid.uuid4()),
        )

        logger.info(
            f"Health Check worker created successfully for task queue: {task_queue}"
        )
        logger.info(
            f"Registered {len(workflows or [])} workflows and {len(activities or [])} activities"
        )
        if workflows:
            logger.info(f"Workflows: {[w.__name__ for w in workflows]}")
        if activities:
            logger.info(f"Activities: {[a.__name__ for a in activities]}")

        # Run the worker (this will block until the worker is stopped)
        await health_check_worker.run()

    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise
    finally:
        # Cleanup
        if health_check_worker:
            logger.info("Shutting down worker...")
            await health_check_worker.shutdown()


def create_agentex_server_worker(
    agent_repo: AgentRepository,
    http_client: httpx.AsyncClient,
    global_dependencies: GlobalDependencies,
) -> asyncio.Task:
    """
    Create the single Temporal worker that serves the `agentex-server` task queue.

    Registers ALL workflows + activities that run on this queue — health checks
    AND retention cleanup — in one worker. Workers polling the same task queue
    must register the same set of types (the queue is not typed), so these live
    together in one worker rather than as separate processes/containers.
    """
    task_queue = os.environ.get("AGENTEX_SERVER_TASK_QUEUE", AGENTEX_SERVER_TASK_QUEUE)

    logger.info("Starting agentex-server Temporal worker")
    logger.info(f"Task queue: {task_queue}")

    health_check_activities = HealthCheckActivities(
        agent_repo=agent_repo,
        http_client=http_client,
    )

    retention_use_case = build_task_retention_use_case(global_dependencies)
    # Reuse the repository the factory already built (avoids a duplicate
    # TaskRepository) via the use case's stable accessor.
    retention_activities = RetentionCleanupActivities(
        task_repository=retention_use_case.task_repository,
        use_case=retention_use_case,
    )

    return asyncio.create_task(
        run_worker(
            task_queue=task_queue,
            workflows=[
                HealthCheckWorkflow,
                RetentionCleanupSweepWorkflow,
                RetentionCleanupTaskWorkflow,
            ],
            activities=[
                health_check_activities.check_status_activity,
                health_check_activities.update_agent_status_activity,
                retention_activities.load_cleanup_config,
                retention_activities.find_cleanup_candidates,
                retention_activities.find_multi_agent_cleanup_candidates,
                retention_activities.clean_task,
            ],
            max_workers=50,
            max_concurrent_activities=50,
        )
    )


async def main() -> None:
    """Main entry point for the agentex-server Temporal worker."""
    try:
        await startup_global_dependencies()
        global_dependencies = GlobalDependencies()

        engine = database_async_read_write_engine()
        session_maker = database_async_read_write_session_maker(engine)
        read_only_session_maker = database_async_read_only_session_maker(engine)
        agent_repo = AgentRepository(session_maker, read_only_session_maker)

        worker_task = create_agentex_server_worker(
            agent_repo=agent_repo,
            http_client=httpx_client(),
            global_dependencies=global_dependencies,
        )
        await worker_task

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down worker...")
        if health_check_worker:
            await health_check_worker.shutdown()
    except Exception as e:
        logger.error(f"Worker startup failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
