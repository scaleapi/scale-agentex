from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import AgentORM, TaskAgentORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.entities.agents import AgentEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentRepository(PostgresCRUDRepository[AgentORM, AgentEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
    ):
        super().__init__(async_read_write_session_maker, AgentORM, AgentEntity)

    async def list(self, filters: dict | None = None) -> list[AgentEntity]:
        """
        List agents with optional filtering.

        Args:
            filters: Dictionary of filters to apply. Currently supports:
                    - task_id: Filter agents by task ID using the join table
        """
        if not filters or "task_id" not in filters:
            return await super().list(filters)

        async with self.start_async_db_session(allow_writes=True) as session:
            # Build query with join to task_agents table
            query = (
                select(AgentORM)
                .join(TaskAgentORM, AgentORM.id == TaskAgentORM.agent_id)
                .where(TaskAgentORM.task_id == filters["task_id"])
            )

            result = await session.execute(query)
            agents = result.scalars().all()
            return [AgentEntity.model_validate(agent) for agent in agents]

    @asynccontextmanager
    async def acquire_advisory_lock(
        self,
        lock_key: int,
    ) -> AsyncIterator[bool]:
        async with (
            self.start_async_db_session(allow_writes=True) as session,
            async_sql_exception_handler(),
        ):
            yield await session.scalar(select(func.pg_try_advisory_xact_lock(lock_key)))


DAgentRepository = Annotated[AgentRepository, Depends(AgentRepository)]
