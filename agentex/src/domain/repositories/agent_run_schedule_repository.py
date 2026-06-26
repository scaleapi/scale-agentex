from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.orm import AgentRunScheduleORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.agent_run_schedules import AgentRunScheduleEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentRunScheduleRepository(
    PostgresCRUDRepository[AgentRunScheduleORM, AgentRunScheduleEntity]
):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            AgentRunScheduleORM,
            AgentRunScheduleEntity,
        )

    async def list_by_agent_id(
        self,
        agent_id: str,
        limit: int | None = None,
        page_number: int | None = None,
    ) -> list[AgentRunScheduleEntity]:
        """List run schedules for a single agent, newest first.

        Soft-deleted schedules are excluded.
        """
        query = select(AgentRunScheduleORM).where(
            AgentRunScheduleORM.agent_id == agent_id,
            AgentRunScheduleORM.deleted_at.is_(None),
        )
        return await super().list(
            query=query,
            order_by="created_at",
            order_direction="desc",
            limit=limit,
            page_number=page_number,
        )

    async def get_by_agent_id_and_name(
        self, agent_id: str, name: str, include_deleted: bool = False
    ) -> AgentRunScheduleEntity | None:
        """Get a run schedule by its (agent_id, name) natural key, or None.

        Soft-deleted schedules are excluded unless ``include_deleted`` is set
        (used by create to keep a deleted name reserved — names are not reusable).
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            query = select(AgentRunScheduleORM).where(
                AgentRunScheduleORM.agent_id == agent_id,
                AgentRunScheduleORM.name == name,
            )
            if not include_deleted:
                query = query.where(AgentRunScheduleORM.deleted_at.is_(None))
            result = await session.execute(query)
            row = result.scalars().first()
            return AgentRunScheduleEntity.model_validate(row) if row else None

    async def get_by_agent_id_and_name_or_raise(
        self, agent_id: str, name: str, include_deleted: bool = False
    ) -> AgentRunScheduleEntity:
        """Get a run schedule by (agent_id, name) or raise ItemDoesNotExist."""
        schedule = await self.get_by_agent_id_and_name(
            agent_id, name, include_deleted=include_deleted
        )
        if schedule is None:
            raise ItemDoesNotExist(
                f"Run schedule '{name}' for agent '{agent_id}' does not exist."
            )
        return schedule


DAgentRunScheduleRepository = Annotated[
    AgentRunScheduleRepository, Depends(AgentRunScheduleRepository)
]
