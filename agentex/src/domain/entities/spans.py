from datetime import datetime
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class SpanEntity(BaseModel):
    id: str = Field(
        ...,
        title="Unique Span ID",
    )
    trace_id: str = Field(
        ...,
        title="The trace ID for this span",
    )
    parent_id: str | None = Field(
        None,
        title="The parent span ID if this is a child span",
    )
    name: str = Field(
        ...,
        title="The name of the span",
    )
    start_time: datetime = Field(
        ...,
        title="The time the span started",
    )
    end_time: datetime | None = Field(
        None,
        title="The time the span ended",
    )
    input: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="The input data for the span",
    )
    output: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="The output data from the span",
    )
    data: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="Additional data associated with the span",
    )
