from typing import Annotated, Any

from fastapi import Depends
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.orm import SpanORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.entities.spans import SpanEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class SpanRepository(PostgresCRUDRepository[SpanORM, SpanEntity]):
    def __init__(
        self, async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker
    ):
        super().__init__(async_read_write_session_maker, SpanORM, SpanEntity)

    def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
    ) -> list[SpanEntity]:
        return super().list(
            filters, order_by="start_time", limit=limit, page_number=page_number
        )


DSpanRepository = Annotated[SpanRepository, Depends(SpanRepository)]
