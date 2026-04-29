"""
Temporal activities for health check workflows.

This module provides focused activities for checking the status of an agent via its ACP endpoint.
Each activity has a single responsibility, allowing the workflow to orchestrate
the status checks and the database updates.
"""

from src.domain.entities.agents import AgentStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.services.agent_protocol_gateway import AgentProtocolGateway
from src.utils.logging import make_logger
from temporalio import activity

logger = make_logger(__name__)


# Activity names
CHECK_STATUS_ACTIVITY = "check_status_activity"
UPDATE_AGENT_STATUS_ACTIVITY = "update_agent_status_activity"


class HealthCheckException(Exception):
    """Exception for health check activities."""

    pass


class HealthCheckActivities:
    """
    Activities for health check.

    Each activity is focused on a single responsibility:
    - Checking agent health via endpoint
    - Updating agent status in the database
    """

    def __init__(
        self, agent_repo: AgentRepository, protocol_gateway: AgentProtocolGateway
    ):
        """Initialize with agent repository and protocol gateway."""
        self.agent_repo = agent_repo
        self.protocol_gateway = protocol_gateway

    @activity.defn(name=CHECK_STATUS_ACTIVITY)
    async def check_status_activity(self, agent_id: str, acp_url: str) -> bool:
        """
        Check the status of an agent via its ACP endpoint.

        Args:
            agent_id: The ID of the agent to check
            acp_url: The URL of the agent's ACP endpoint

        Returns:
            bool: True if the agent is healthy, False otherwise
        """
        logger.info(f"Checking status of agent {agent_id} via {acp_url}")
        return await self.protocol_gateway.check_health(
            agent_id=agent_id, service_url=acp_url
        )

    @activity.defn(name=UPDATE_AGENT_STATUS_ACTIVITY)
    async def update_agent_status_activity(self, agent_id: str, status: str) -> None:
        """
        Update the status of an agent in the database.
        """
        try:
            # Get agent
            agent = await self.agent_repo.get(id=agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")
            new_status = AgentStatus(status)
            if agent.status == new_status:
                return
            agent.status = new_status
            agent.status_reason = "Agent health check reported " + status
            await self.agent_repo.update(item=agent)
            logger.info(f"Updated agent {agent_id} status to {status}")
        except Exception as e:
            logger.error(f"Failed to update agent {agent_id} status: {e}")
            raise
