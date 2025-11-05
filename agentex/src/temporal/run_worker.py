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
    database_async_read_write_engine,
    database_async_read_write_session_maker,
    httpx_client,
    startup_global_dependencies,
)
from src.config.environment_variables import EnvironmentVariables
from src.domain.repositories.agent_repository import AgentRepository
from src.temporal.activities.healthcheck_activities import HealthCheckActivities
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Task queue name for agentex server operations
AGENTEX_SERVER_TASK_QUEUE = "agentex-server"

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
        metrics_url = f"http://[{host_url}]:4317" if host_url else None
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


def create_health_check_worker(
    agent_repo: AgentRepository, http_client: httpx.AsyncClient
) -> asyncio.Task:
    """
    Create a Health Check worker.
    """
    # Get task queue from environment or use default
    task_queue = os.environ.get("AGENTEX_SERVER_TASK_QUEUE", AGENTEX_SERVER_TASK_QUEUE)

    logger.info("Starting Temporal Health Check Worker")
    logger.info(f"Task queue: {task_queue}")

    # Create activities instance with dependencies
    health_check_activities = HealthCheckActivities(
        agent_repo=agent_repo,
        http_client=httpx_client(),
    )

    # Extract activity methods
    activities = [
        health_check_activities.check_status_activity,
        health_check_activities.update_agent_status_activity,
    ]

    # Create and run worker task
    return asyncio.create_task(
        run_worker(
            task_queue=task_queue,
            workflows=[HealthCheckWorkflow],
            activities=activities,
            max_workers=50,
            max_concurrent_activities=50,
        )
    )


async def main() -> None:
    """
    Main entry point for the Health Check worker.
    """
    try:
        # Initialize global dependencies for this thread
        await startup_global_dependencies()
        # Create session maker
        engine = database_async_read_write_engine()
        session_maker = database_async_read_write_session_maker(engine)
        agent_repo = AgentRepository(session_maker)
        health_check_worker_task = create_health_check_worker(
            agent_repo=agent_repo,
            http_client=httpx_client(),
        )
        # Wait for the worker to complete
        await health_check_worker_task

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down worker...")
        if health_check_worker:
            await health_check_worker.shutdown()
    except Exception as e:
        logger.error(f"Worker startup failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
