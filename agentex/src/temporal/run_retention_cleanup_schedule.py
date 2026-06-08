"""
Create the Temporal Schedule that drives the scheduled task-retention cleanup.

Runs at startup (mirrors run_healthcheck_workflow.py). No-op unless
RETENTION_CLEANUP_ENABLED is true and Temporal is configured.
Idempotent: if the schedule already exists, it is left as-is.

The schedule carries NO policy args (no allowlist, idle_days, page_size, or
max_in_flight). Those are read at sweep runtime via the load_cleanup_config
activity so changing a RETENTION_CLEANUP_* env var and restarting the worker
takes effect on the next scheduled run without recreating the schedule.
Only the cron expression and workflow identity are baked into the schedule.

Fail-closed behaviour is preserved at runtime: if the allowlist is empty the
discovery activity returns no candidates and the sweep completes immediately.
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
    if not TemporalClientFactory.is_temporal_configured(env):
        logger.error("Temporal is not configured; skipping schedule creation")
        return

    if not env.RETENTION_CLEANUP_AGENT_ALLOWLIST:
        logger.info(
            "Retention cleanup agent allowlist is empty; the sweep will discover "
            "no candidates at runtime (fail-closed by policy, not by schedule)"
        )

    task_queue = env.AGENTEX_SERVER_TASK_QUEUE or AGENTEX_SERVER_TASK_QUEUE
    adapter = TemporalAdapter(temporal_client=global_dependencies.temporal_client)

    try:
        await adapter.create_schedule(
            schedule_id=SCHEDULE_ID,
            workflow=RetentionCleanupSweepWorkflow.run,
            workflow_id=WORKFLOW_ID,
            args=[],
            task_queue=task_queue,
            cron_expressions=[env.RETENTION_CLEANUP_CRON],
        )
        logger.info(
            "Created retention-cleanup schedule (policy read at runtime)",
            extra={"cron": env.RETENTION_CLEANUP_CRON},
        )
    except TemporalScheduleAlreadyExistsError:
        logger.info("Retention-cleanup schedule already exists; leaving as-is")


if __name__ == "__main__":
    asyncio.run(main())
