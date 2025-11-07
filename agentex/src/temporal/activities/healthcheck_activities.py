"""
Temporal activities for health check workflows.

This module provides focused activities for checking the status of an agent via its ACP endpoint.
Each activity has a single responsibility, allowing the workflow to orchestrate
the status checks and the database updates.
"""

import json

import httpx
from src.domain.entities.agents import AgentStatus
from src.domain.repositories.agent_repository import AgentRepository
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

    def __init__(self, agent_repo: AgentRepository, http_client: httpx.AsyncClient):
        """Initialize with session maker and http client."""
        self.agent_repo = agent_repo
        self.http_client = http_client

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
        try:
            response = await self.http_client.get(f"{acp_url}/healthz", timeout=5)
            if response.status_code != 200:
                logger.error(
                    f"Agent {agent_id} returned non-200 status: {response.status_code}"
                )
                return False
            try:
                parsed_response = response.json()
                status = parsed_response.get("status")
                if status != "healthy":
                    logger.error(
                        f"Agent {agent_id} returned non-healthy status: {status}"
                    )
                    return False
                response_agent_id = parsed_response.get("agent_id")
                if response_agent_id and response_agent_id != agent_id:
                    logger.error(
                        f"Agent {agent_id} returned unexpected agent ID: {response_agent_id}"
                    )
                    return False
            except json.JSONDecodeError:
                logger.error(
                    f"Agent {agent_id} returned non-JSON response: {response.text}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to check status of agent {agent_id}: {e}")
        return False

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
