import asyncio

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.client_factory import TemporalClientFactory
from src.adapters.temporal.exceptions import (
    TemporalWorkflowAlreadyExistsError,
)
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
)
from src.config.environment_variables import EnvironmentVariables
from src.domain.repositories.agent_repository import AgentRepository
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow
from src.utils.logging import make_logger

logger = make_logger(__name__)


async def main() -> None:
    """
    Main entry point for ensuring a health check workflow is running for each agent.
    """
    # Initialize global dependencies for this thread
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()

    # Check if health check workflow is enabled and configured
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
    # Check if Temporal is configured
    if not TemporalClientFactory.is_temporal_configured(environment_variables):
        logger.error("Temporal is not configured, skipping workflow creation")
        return

    # Initialize repository and list agents
    engine = database_async_read_write_engine()
    session_maker = database_async_read_write_session_maker(engine)
    agent_repo = AgentRepository(session_maker)
    agents = await agent_repo.list()

    adapter = TemporalAdapter(temporal_client=global_dependencies.temporal_client)
    logger.info(f"Adding Health Check workflows to task queue: {task_queue}")
    # Try to add health check workflows to task queue for each agent
    for agent in agents:
        try:
            await adapter.start_workflow(
                workflow_id=f"healthcheck_workflow_{agent.id}",
                workflow=HealthCheckWorkflow,
                args=[{"agent_id": agent.id, "acp_url": agent.acp_url}],
                task_queue=task_queue,
            )
        except TemporalWorkflowAlreadyExistsError:
            # Expected if workflow is already running for existing agent registration
            logger.info(f"Health check workflow already exists for agent {agent.id}")
        except Exception as e:
            # Unexpected error, don't raise here to continue with the next agent
            logger.error(
                f"Failed to start health check workflow for agent {agent.id}: {e}"
            )


if __name__ == "__main__":
    asyncio.run(main())
