"""
Create the Temporal Schedule that drives the scheduled task-retention cleanup.

Runs at startup (mirrors run_healthcheck_workflow.py). No-op unless
RETENTION_CLEANUP_ENABLED is true and an agent allowlist is configured
(fail-closed). Idempotent: if the schedule already exists, it is left as-is.
"""

import asyncio

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.client_factory import TemporalClientFactory
from src.adapters.temporal.exceptions import TemporalScheduleAlreadyExistsError
from src.config.dependencies import GlobalDependencies
from src.config.environment_variables import EnvironmentVariables
from src.temporal.run_worker import AGENTEX_SERVER_TASK_QUEUE
from src.temporal.workflows.retention_cleanup_workflow import (
    RetentionCleanupSweepWorkflow,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

SCHEDULE_ID = "retention-cleanup-sweep"
WORKFLOW_ID = "retention-cleanup-sweep"


async def main() -> None:
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()

    env = EnvironmentVariables.refresh()
    if not env or not env.RETENTION_CLEANUP_ENABLED:
        logger.info("Retention cleanup is not enabled; skipping schedule creation")
        return
    if not env.RETENTION_CLEANUP_AGENT_ALLOWLIST:
        logger.warning(
            "Retention cleanup enabled but agent allowlist is empty (fail-closed); "
            "skipping schedule creation"
        )
        return
    if not TemporalClientFactory.is_temporal_configured(env):
        logger.error("Temporal is not configured; skipping schedule creation")
        return

    task_queue = env.AGENTEX_SERVER_TASK_QUEUE or AGENTEX_SERVER_TASK_QUEUE
    adapter = TemporalAdapter(temporal_client=global_dependencies.temporal_client)

    workflow_args = {
        "idle_days": env.RETENTION_CLEANUP_IDLE_DAYS,
        "agent_names": env.RETENTION_CLEANUP_AGENT_ALLOWLIST,
        "page_size": env.RETENTION_CLEANUP_PAGE_SIZE,
        "max_in_flight": env.RETENTION_CLEANUP_MAX_IN_FLIGHT,
    }

    try:
        await adapter.create_schedule(
            schedule_id=SCHEDULE_ID,
            workflow=RetentionCleanupSweepWorkflow.run,
            workflow_id=WORKFLOW_ID,
            args=[workflow_args],
            task_queue=task_queue,
            cron_expressions=[env.RETENTION_CLEANUP_CRON],
        )
        logger.info(
            "Created retention-cleanup schedule",
            extra={"cron": env.RETENTION_CLEANUP_CRON, "args": workflow_args},
        )
    except TemporalScheduleAlreadyExistsError:
        logger.info("Retention-cleanup schedule already exists; leaving as-is")


if __name__ == "__main__":
    asyncio.run(main())
