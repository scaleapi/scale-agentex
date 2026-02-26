from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import desc, select
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.orm import AgentORM, DeploymentHistoryORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.agents import AgentEntity
from src.domain.entities.deployment_history import DeploymentHistoryEntity
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class DeploymentHistoryRepository(
    PostgresCRUDRepository[DeploymentHistoryORM, DeploymentHistoryEntity]
):
    """Repository for deployment history operations."""

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            DeploymentHistoryORM,
            DeploymentHistoryEntity,
        )

    async def list(
        self,
        filters: dict | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[DeploymentHistoryEntity]:
        """
        List deployment history with optional filtering.

        Args:
            filters: Dictionary of filters to apply. Currently supports:
                    - agent_id: Filter agents by agent ID using the join table
            order_by: Field to order by
            order_direction: Order direction (asc or desc)
        """
        query = select(DeploymentHistoryORM)
        if filters and "agent_id" in filters:
            query = query.join(
                AgentORM, AgentORM.id == DeploymentHistoryORM.agent_id
            ).where(AgentORM.id == filters["agent_id"])
        return await super().list(
            filters=filters,
            query=query,
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
        query = (
            select(DeploymentHistoryORM)
            .join(AgentORM, AgentORM.id == DeploymentHistoryORM.agent_id)
            .where(AgentORM.id == agent_id)
            .order_by(desc(DeploymentHistoryORM.deployment_timestamp))
            .limit(1)
        )
        async with self.start_async_db_session(allow_writes=False) as session:
            result = await session.execute(query)
            orm_results = result.scalars().all()
            return (
                DeploymentHistoryEntity.model_validate(orm_results[0])
                if orm_results
                else None
            )

    async def create_from_agent(
        self, agent: AgentEntity
    ) -> DeploymentHistoryEntity | None:
        """
        Create a new deployment history record from an agent.

        Returns:
            DeploymentHistoryEntity: The created deployment history record, or None if skipped.

        Skips and returns None in the following cases:
            - The agent has no registration metadata.
            - The registration metadata does not contain a commit hash.
            - The registration metadata does not contain a branch name.
            - The last deployment for the agent has the same commit hash as the current one.
        """
        registration_metadata = agent.registration_metadata
        if not registration_metadata:
            logger.info(
                f"No registration metadata found for agent {agent.id}, skipping deployment history update"
            )
            return

        commit_hash = agent.registration_metadata.get("agent_commit")
        if not commit_hash:
            logger.info(
                f"No commit hash found for agent {agent.id}, skipping deployment history update"
            )
            return

        branch_name = registration_metadata.get("branch_name")
        if not branch_name:
            logger.info(
                f"No branch name found for agent {agent.id}, skipping deployment history update"
            )
            return

        last_deployment = await self.get_last_deployment_for_agent(agent_id=agent.id)
        if last_deployment and last_deployment.commit_hash == commit_hash:
            logger.info(
                f"Last deployment for agent {agent.id} is the same as the current deployment, skipping update"
            )
            return

        logger.info(f"Creating new deployment history entry for agent {agent.id}")
        return await self.create(
            DeploymentHistoryEntity(
                id=orm_id(),
                agent_id=agent.id,
                author_name=registration_metadata.get("author_name", "N/A"),
                author_email=registration_metadata.get("author_email", "N/A"),
                branch_name=branch_name,
                build_timestamp=registration_metadata.get(
                    "build_timestamp", datetime.now(UTC)
                ),
                deployment_timestamp=agent.registered_at or datetime.now(UTC),
                commit_hash=commit_hash,
            )
        )


# Type alias for dependency injection
DDeploymentHistoryRepository = Annotated[
    DeploymentHistoryRepository, Depends(DeploymentHistoryRepository)
]
