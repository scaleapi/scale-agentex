from datetime import datetime
from typing import Annotated

from fastapi import Depends

from src.domain.entities.deployment_history import DeploymentHistoryEntity
from src.domain.repositories.deployment_history_repository import (
    DDeploymentHistoryRepository,
)
from src.utils.ids import orm_id


class DeploymentHistoryUseCase:
    """Use case for deployment history operations."""

    def __init__(self, deployment_history_repository: DDeploymentHistoryRepository):
        self.deployment_history_repository = deployment_history_repository

    async def get_deployment(self, deployment_id: str) -> DeploymentHistoryEntity:
        """
        Get a specific deployment by ID.

        Args:
            deployment_id: The deployment ID

        Returns:
            The deployment history entity

        Raises:
            ItemDoesNotExist: If deployment is not found
        """
        return await self.deployment_history_repository.get(id=deployment_id)

    async def list_deployments(
        self,
        limit: int,
        page_number: int,
        order_by: str | None = None,
        order_direction: str = "desc",
        **filters,
    ) -> list[DeploymentHistoryEntity]:
        """
        List deployment records with optional filtering.

        Args:
            agent_id: Filter by agent ID
            commit_hash: Filter by commit hash
            author_email: Filter by author email
            limit: Maximum number of results to return
            offset: Number of results to skip
            start_date: Filter deployments built after this date
            end_date: Filter deployments built before this date
            order_by: Field to order by
            order_direction: Order direction (asc or desc)

        Returns:
            List of deployment history entities
        """
        # Use the basic list method from the repository
        return await self.deployment_history_repository.list(
            filters=filters,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )

    async def get_last_deployment_for_agent(
        self,
        agent_id: str,
    ) -> DeploymentHistoryEntity | None:
        """
        Get last deployment record for a specific agent.

        Args:
            agent_id: The agent ID to filter by

        Returns:
            Last deployment history entity for the agent
        """
        return await self.deployment_history_repository.get_last_deployment_for_agent(
            agent_id=agent_id
        )

    async def create_deployment(
        self,
        agent_id: str,
        author_name: str,
        author_email: str,
        branch_name: str,
        build_timestamp: datetime,
        deployment_timestamp: datetime,
        commit_hash: str,
    ) -> DeploymentHistoryEntity:
        """
        Create a new deployment record.

        Args:
            agent_id: The agent ID this deployment belongs to
            author_name: Name of the commit author
            author_email: Email of the commit author
            build_timestamp: When the build was created
            deployment_timestamp: When this deployment was first seen in the system
            commit_hash: Git commit hash for this deployment

        Returns:
            The created deployment history entity
        """
        deployment_entity = DeploymentHistoryEntity(
            id=orm_id(),
            agent_id=agent_id,
            author_name=author_name,
            author_email=author_email,
            branch_name=branch_name,
            build_timestamp=build_timestamp,
            deployment_timestamp=deployment_timestamp,
            commit_hash=commit_hash,
        )

        return await self.deployment_history_repository.create(deployment_entity)


# Type alias for dependency injection
DDeploymentHistoryUseCase = Annotated[
    DeploymentHistoryUseCase, Depends(DeploymentHistoryUseCase)
]
