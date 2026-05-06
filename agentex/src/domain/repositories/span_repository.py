from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import or_, select
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.orm import SpanORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.spans import SpanEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class SpanRepository(PostgresCRUDRepository[SpanORM, SpanEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            SpanORM,
            SpanEntity,
        )

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[SpanEntity]:
        # Default to start_time if no order_by specified
        effective_order_by = order_by or "start_time"

        # Filtering by task_id matches both the new task_id column and historical
        # rows where the value was stored in trace_id. The task_id column was
        # added late in the table's life and the prod backfill is run out-of-band
        # rather than via migration (see docs/runbooks/spans-task-id-backfill.md),
        # so old rows can have task_id NULL even when they belong to a task. For
        # task-scoped spans, trace_id holds the task id, so we OR the two columns
        # at read time. Both columns are indexed.
        #
        # The OR fallback is skipped when task_id is None — applying it would
        # expand to (task_id IS NULL OR trace_id IS NULL), which on a large
        # spans table where virtually all historical rows have task_id NULL
        # would return an enormous, unintended result set. A None task_id
        # filter falls through to the parent's normal IS NULL handling.
        if filters and filters.get("task_id") is not None:
            remaining_filters = {k: v for k, v in filters.items() if k != "task_id"}
            task_id_value = filters["task_id"]
            query = select(self.orm).where(
                or_(SpanORM.task_id == task_id_value, SpanORM.trace_id == task_id_value)
            )
            return await super().list(
                filters=remaining_filters or None,
                query=query,
                order_by=effective_order_by,
                order_direction=order_direction,
                limit=limit,
                page_number=page_number,
            )

        return await super().list(
            filters=filters,
            order_by=effective_order_by,
            order_direction=order_direction,
            limit=limit,
            page_number=page_number,
        )


DSpanRepository = Annotated[SpanRepository, Depends(SpanRepository)]
