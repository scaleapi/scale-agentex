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
from src.domain.entities.agents import AgentEntity, AgentStatus
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentRepository(PostgresCRUDRepository[AgentORM, AgentEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            AgentORM,
            AgentEntity,
        )

    async def list(
        self,
        filters: dict | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[AgentEntity]:
        """
        List agents with optional filtering.

        Args:
            filters: Dictionary of filters to apply. Currently supports:
                    - task_id: Filter agents by task ID using the join table
            order_by: Field to order by
            order_direction: Direction to order by (asc or desc)
        """
        query = select(AgentORM)
        if filters and "task_id" in filters:
            query = query.join(
                TaskAgentORM, AgentORM.id == TaskAgentORM.agent_id
            ).where(TaskAgentORM.task_id == filters["task_id"])
        query = query.where(AgentORM.status != AgentStatus.DELETED)
        return await super().list(
            filters=filters,
            query=query,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )

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
