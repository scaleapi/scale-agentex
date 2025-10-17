from datetime import datetime
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class CreateSpanRequest(BaseModel):
    id: str | None = Field(
        None,
        title="Unique Span ID",
        description="Unique identifier for the span. If not provided, an ID will be generated.",
    )
    trace_id: str = Field(
        ...,
        title="The trace ID for this span",
        description="Unique identifier for the trace this span belongs to",
    )
    parent_id: str | None = Field(
        None,
        title="The parent span ID if this is a child span",
        description="ID of the parent span if this is a child span in a trace",
    )
    name: str = Field(
        ...,
        title="The name of the span",
        description="Name that describes what operation this span represents",
    )
    start_time: datetime = Field(
        ..., title="The start time of the span", description="The time the span started"
    )
    end_time: datetime | None = Field(
        None, title="The end time of the span", description="The time the span ended"
    )
    input: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="The input data for the span",
        description="Input parameters or data for the operation",
    )
    output: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="The output data from the span",
        description="Output data resulting from the operation",
    )
    data: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="Additional data associated with the span",
        description="Any additional metadata or context for the span",
    )


class UpdateSpanRequest(BaseModel):
    trace_id: str | None = Field(
        None,
        title="The trace ID for this span",
        description="Unique identifier for the trace this span belongs to",
    )
    parent_id: str | None = Field(
        None,
        title="The parent span ID if this is a child span",
        description="ID of the parent span if this is a child span in a trace",
    )
    name: str | None = Field(
        None,
        title="The name of the span",
        description="Name that describes what operation this span represents",
    )
    start_time: datetime | None = Field(
        None,
        title="The start time of the span",
        description="The time the span started",
    )
    end_time: datetime | None = Field(
        None, title="The end time of the span", description="The time the span ended"
    )
    input: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="The input data for the span",
        description="Input parameters or data for the operation",
    )
    output: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="The output data from the span",
        description="Output data resulting from the operation",
    )
    data: dict[str, Any] | list[dict[str, Any]] | None = Field(
        None,
        title="Additional data associated with the span",
        description="Any additional metadata or context for the span",
    )


class Span(CreateSpanRequest):
    id: str = Field(
        ...,
        title="Unique Span ID",
    )
