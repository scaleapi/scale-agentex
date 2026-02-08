from typing import Annotated

from fastapi import Depends
from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import EventORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.events import EventEntity
from src.domain.entities.task_messages import TaskMessageContentEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class EventRepository(PostgresCRUDRepository[EventORM, EventEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            EventORM,
            EventEntity,
        )

    async def create(
        self,
        id: str,
        task_id: str,
        agent_id: str,
        content: TaskMessageContentEntity | None = None,
    ) -> EventEntity:
        """Create an event using INSERT ... RETURNING to get sequence_id in one query."""
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                insert(EventORM)
                .values(
                    id=id,
                    task_id=task_id,
                    agent_id=agent_id,
                    content=content.model_dump(mode="json") if content else None,
                )
                .returning(EventORM)
            )

            result = await session.execute(stmt)
            orm = result.scalar_one()
            await session.commit()
            return self.entity.model_validate(orm)

    async def list_events_after_last_processed(
        self,
        task_id: str,
        agent_id: str,
        last_processed_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[EventEntity]:
        """
        List events for a specific task and agent, optionally filtering for events
        after a specific event ID.

        Args:
            task_id: The task ID to filter by
            agent_id: The agent ID to filter by
            last_processed_event_id: Optional event ID to filter events after
            limit: Optional limit on number of results

        Returns:
            List of Event objects ordered by sequence_id
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            # If last_processed_event_id is provided, first find its sequence_id
            last_sequence_id = None
            if last_processed_event_id is not None:
                sequence_query = select(EventORM.sequence_id).where(
                    EventORM.id == last_processed_event_id
                )
                result = await session.execute(sequence_query)
                last_sequence_id = result.scalar_one_or_none()

            # Build the query with filters
            query = select(EventORM).where(
                and_(
                    EventORM.task_id == task_id,
                    EventORM.agent_id == agent_id,
                )
            )

            # Add sequence filter if we found a sequence_id
            if last_sequence_id is not None:
                query = query.where(EventORM.sequence_id > last_sequence_id)

            # Order by sequence ID for consistent ordering
            query = query.order_by(EventORM.sequence_id)

            # Add limit if provided
            if limit is not None:
                query = query.limit(limit)

            result = await session.execute(query)
            event_orms = result.scalars().all()

            return [EventEntity.model_validate(orm) for orm in event_orms]


DEventRepository = Annotated[EventRepository, Depends(EventRepository)]
