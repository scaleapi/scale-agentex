"""Create the recurring Temporal schedule that restores missing health monitors."""

import asyncio

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.client_factory import TemporalClientFactory
from src.adapters.temporal.exceptions import TemporalScheduleAlreadyExistsError
from src.config.dependencies import GlobalDependencies
from src.config.environment_variables import EnvironmentVariables
from src.temporal.workflows.healthcheck_reconciliation_workflow import (
    HealthCheckReconciliationWorkflow,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

SCHEDULE_ID = "healthcheck-reconciliation-sweep"
WORKFLOW_ID = "healthcheck-reconciliation-sweep"
RECONCILIATION_INTERVAL_SECONDS = 300
DEFAULT_TASK_QUEUE = "agentex-server"


async def ensure_reconciliation_schedule(adapter, task_queue: str) -> None:
    """Create the reconciliation schedule, or leave the existing one intact."""
    try:
        await adapter.create_schedule(
            schedule_id=SCHEDULE_ID,
            workflow=HealthCheckReconciliationWorkflow.run,
            workflow_id=WORKFLOW_ID,
            args=[],
            task_queue=task_queue,
            interval_seconds=RECONCILIATION_INTERVAL_SECONDS,
            overlap_policy="skip",
        )
        logger.info("Created health-check reconciliation schedule")
    except TemporalScheduleAlreadyExistsError:
        logger.info(
            "Health-check reconciliation schedule already exists; leaving as-is"
        )


async def main() -> None:
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()

    env = EnvironmentVariables.refresh()
    if not env or not env.ENABLE_HEALTH_CHECK_WORKFLOW:
        logger.info("Health checks are not enabled; skipping reconciliation schedule")
        return
    if not TemporalClientFactory.is_temporal_configured(env):
        logger.error("Temporal is not configured; skipping reconciliation schedule")
        return

    task_queue = env.AGENTEX_SERVER_TASK_QUEUE or DEFAULT_TASK_QUEUE
    adapter = TemporalAdapter(temporal_client=global_dependencies.temporal_client)
    await ensure_reconciliation_schedule(adapter, task_queue)


if __name__ == "__main__":
    asyncio.run(main())
