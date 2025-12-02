from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends

from src.domain.entities.spans import SpanEntity
from src.domain.repositories.span_repository import DSpanRepository
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class SpanUseCase:
    def __init__(self, span_repository: DSpanRepository):
        logger.info("Initializing SpanUseCase")
        self.span_repo = span_repository

    async def create(
        self,
        name: str,
        trace_id: str,
        id: str | None = None,
        parent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> SpanEntity:
        """
        Create a new span with the given parameters
        """
        # Generate ID if not provided
        if id is None:
            id = orm_id()

        span = SpanEntity(
            id=id,
            trace_id=trace_id,
            parent_id=parent_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            input=input_data,
            output=output_data,
            data=data,
        )
        return await self.span_repo.create(span)

    async def partial_update(
        self,
        id: str,
        trace_id: str | None = None,
        name: str | None = None,
        parent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> SpanEntity:
        """
        Update an existing span with partial data
        """
        # Get the existing span
        span = await self.span_repo.get(id=id)

        # Apply partial updates for all fields
        if trace_id is not None:
            span.trace_id = trace_id

        if name is not None:
            span.name = name

        if parent_id is not None:
            span.parent_id = parent_id

        if start_time is not None:
            span.start_time = start_time

        if end_time is not None:
            span.end_time = end_time

        if input_data is not None:
            span.input = input_data

        if output_data is not None:
            span.output = output_data

        if data is not None:
            # Merge with existing data if present
            if span.data:
                span.data.update(data)
            else:
                span.data = data

        return await self.span_repo.update(span)

    async def get(self, span_id: str) -> SpanEntity:
        """
        Get a span by ID
        """
        return await self.span_repo.get(id=span_id)

    async def list(
        self,
        limit: int,
        page_number: int,
        trace_id: str | None = None,
        order_by: str | None = None,
        order_direction: str = "desc",
    ) -> list[SpanEntity]:
        """
        List all spans for a given trace ID
        """
        # Note: This would require custom implementation in the repository
        # or filtering after fetching all spans

        if trace_id:
            filters = {"trace_id": trace_id}
        else:
            filters = None
        return await self.span_repo.list(
            filters=filters,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )


DSpanUseCase = Annotated[SpanUseCase, Depends(SpanUseCase)]
