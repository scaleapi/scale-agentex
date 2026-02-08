from typing import Annotated, Any

from fastapi import Depends
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
        return await super().list(
            filters=filters,
            order_by=effective_order_by,
            order_direction=order_direction,
            limit=limit,
            page_number=page_number,
        )


DSpanRepository = Annotated[SpanRepository, Depends(SpanRepository)]
