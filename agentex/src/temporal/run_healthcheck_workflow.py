import asyncio

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.client_factory import TemporalClientFactory
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
)
from src.config.environment_variables import EnvironmentVariables
from src.domain.repositories.agent_repository import AgentRepository
from src.temporal.healthcheck_reconciliation import (
    MONITORED_AGENT_PAGE_SIZE,
    MONITORED_AGENT_STATUSES,
    reconcile_healthcheck_workflows,
)
from src.temporal.run_healthcheck_reconciliation_schedule import (
    ensure_reconciliation_schedule,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Kept as module exports for callers/tests that use the bootstrap script's policy.
__all__ = ["MONITORED_AGENT_PAGE_SIZE", "MONITORED_AGENT_STATUSES", "main"]


async def main() -> None:
    """Run an immediate health-workflow reconciliation during server startup."""
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()

    environment_variables = EnvironmentVariables.refresh()
    if not environment_variables:
        logger.error("Environment variables are not configured")
        return
    if not environment_variables.ENABLE_HEALTH_CHECK_WORKFLOW:
        logger.info("Health check workflow is not enabled")
        return
    task_queue = environment_variables.AGENTEX_SERVER_TASK_QUEUE
    if not task_queue:
        logger.error("Health check task queue is not configured")
        return
    if not TemporalClientFactory.is_temporal_configured(environment_variables):
        logger.error("Temporal is not configured, skipping workflow creation")
        return

    engine = database_async_read_write_engine()
    session_maker = database_async_read_write_session_maker(engine)
    read_only_session_maker = database_async_read_only_session_maker(engine)
    agent_repo = AgentRepository(session_maker, read_only_session_maker)
    adapter = TemporalAdapter(temporal_client=global_dependencies.temporal_client)

    await ensure_reconciliation_schedule(adapter, task_queue)
    logger.info(f"Adding health check workflows to task queue: {task_queue}")
    totals = await reconcile_healthcheck_workflows(agent_repo, adapter, task_queue)
    logger.info("Health check workflow reconciliation completed", extra=totals)


if __name__ == "__main__":
    asyncio.run(main())
