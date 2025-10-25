from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import desc, select
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.orm import AgentORM, DeploymentHistoryORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.entities.agents import AgentEntity
from src.domain.entities.deployment_history import DeploymentHistoryEntity
from src.utils.ids import orm_id


class DeploymentHistoryRepository(
    PostgresCRUDRepository[DeploymentHistoryORM, DeploymentHistoryEntity]
):
    """Repository for deployment history operations."""

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            DeploymentHistoryORM,
            DeploymentHistoryEntity,
        )

    async def list(self, filters: dict | None = None) -> list[DeploymentHistoryEntity]:
        """
        List deployment history with optional filtering.

        Args:
            filters: Dictionary of filters to apply. Currently supports:
                    - agent_id: Filter agents by agent ID using the join table
        """
        if not filters or "agent_id" not in filters:
            return await super().list(filters)

        # Build query with join to agents table
        query = (
            select(DeploymentHistoryORM)
            .join(AgentORM, AgentORM.id == DeploymentHistoryORM.agent_id)
            .where(DeploymentHistoryORM.agent_id == filters["agent_id"])
        )
        async with self.start_async_db_session(allow_writes=True) as session:
            result = await session.execute(query)
            deployments = result.scalars().all()
            return [
                DeploymentHistoryEntity.model_validate(deployment)
                for deployment in deployments
            ]

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
        async with self.start_async_db_session(allow_writes=True) as session:
            result = await session.execute(query)
            orm_results = result.scalars().all()
            return (
                DeploymentHistoryEntity.model_validate(orm_results[0])
                if orm_results
                else None
            )

    async def create_from_agent(self, agent: AgentEntity) -> DeploymentHistoryEntity:
        """
        Create a new deployment history record from an agent.
        """
        registration_metadata = agent.registration_metadata
        if not registration_metadata:
            raise ValueError("Registration metadata is required")

        commit_hash = registration_metadata.get("agent_commit")
        if not commit_hash:
            raise ValueError("Commit hash is required")

        branch_name = registration_metadata.get("branch_name")
        if not branch_name:
            raise ValueError("Branch name is required")

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
