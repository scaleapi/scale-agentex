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
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.agents import AgentEntity, AgentStatus
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentRepository(PostgresCRUDRepository[AgentORM, AgentEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
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
                    - agent_card_metadata: Dict applied as an exact JSONB
                      containment filter (``@>``) against
                      ``registration_metadata['agent_card']['metadata']``.
            order_by: Field to order by
            order_direction: Direction to order by (asc or desc)
        """
        query = select(AgentORM)
        # Pop out non-column filters that the base repository can't map to a
        # single equality column, so its create_where_clauses_from_filters call
        # doesn't see them.
        filters = dict(filters) if filters else {}
        task_id = filters.pop("task_id", None)
        agent_card_metadata = filters.pop("agent_card_metadata", None)

        if task_id is not None:
            query = query.join(
                TaskAgentORM, AgentORM.id == TaskAgentORM.agent_id
            ).where(TaskAgentORM.task_id == task_id)
        if agent_card_metadata is not None:
            # Top-level JSONB `@>` with the caller's dict wrapped under the same
            # nested shape it will occupy in the stored registration_metadata.
            # `@>` matches when every key/value in the right operand exists at
            # the same path in the left, so agents whose registration_metadata
            # is NULL, missing `agent_card`, or missing `agent_card.metadata`
            # are naturally excluded.
            query = query.where(
                AgentORM.registration_metadata.contains(
                    {"agent_card": {"metadata": agent_card_metadata}}
                )
            )
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
