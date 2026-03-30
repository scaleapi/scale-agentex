from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select, update
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.orm import AgentORM, DeploymentORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.utils.logging import make_logger

logger = make_logger(__name__)


class DeploymentRepository(PostgresCRUDRepository[DeploymentORM, DeploymentEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            DeploymentORM,
            DeploymentEntity,
        )

    async def get_or_none(self, id: str) -> DeploymentEntity | None:
        try:
            return await self.get(id=id)
        except ItemDoesNotExist:
            return None

    async def get_production(self, agent_id: str) -> DeploymentEntity | None:
        query = (
            select(DeploymentORM)
            .where(DeploymentORM.agent_id == agent_id)
            .where(DeploymentORM.is_production.is_(True))
            .limit(1)
        )
        async with self.start_async_db_session(allow_writes=False) as session:
            result = await session.execute(query)
            row = result.scalars().first()
            return DeploymentEntity.model_validate(row) if row else None

    async def list_for_agent(
        self,
        agent_id: str,
        limit: int = 50,
        page_number: int = 1,
        order_by: str | None = None,
        order_direction: str = "desc",
    ) -> list[DeploymentEntity]:
        query = select(DeploymentORM).where(DeploymentORM.agent_id == agent_id)
        return await super().list(
            query=query,
            limit=limit,
            page_number=page_number,
            order_by=order_by or "created_at",
            order_direction=order_direction,
        )

    async def promote(
        self,
        agent_id: str,
        deployment_id: str,
    ) -> DeploymentEntity:
        """Atomically promote a deployment to production.

        In a single transaction:
        1. Unset is_production on the current production deployment
        2. Set is_production=True and promoted_at on the target deployment
        3. Update Agent.production_deployment_id and Agent.acp_url
        """
        async with self.start_async_db_session(allow_writes=True) as session:
            # Validate the target deployment exists and belongs to this agent
            target = await session.execute(
                select(DeploymentORM)
                .where(DeploymentORM.id == deployment_id)
                .where(DeploymentORM.agent_id == agent_id)
            )
            target_deployment = target.scalars().first()
            if not target_deployment:
                raise ItemDoesNotExist(
                    f"Deployment {deployment_id} not found for agent {agent_id}"
                )
            if target_deployment.status != DeploymentStatus.READY:
                raise ValueError(
                    f"Cannot promote deployment with status {target_deployment.status}. "
                    f"Deployment must be in {DeploymentStatus.READY} status."
                )

            now = datetime.now(UTC)

            # Demote current production deployment
            await session.execute(
                update(DeploymentORM)
                .where(DeploymentORM.agent_id == agent_id)
                .where(DeploymentORM.is_production.is_(True))
                .values(is_production=False)
            )

            # Promote target deployment
            target_deployment.is_production = True
            target_deployment.promoted_at = now

            # Update agent's denormalized fields
            await session.execute(
                update(AgentORM)
                .where(AgentORM.id == agent_id)
                .values(
                    production_deployment_id=deployment_id,
                    acp_url=target_deployment.acp_url,
                )
            )

            await session.commit()
            await session.refresh(target_deployment)
            return DeploymentEntity.model_validate(target_deployment)


DDeploymentRepository = Annotated[DeploymentRepository, Depends(DeploymentRepository)]
