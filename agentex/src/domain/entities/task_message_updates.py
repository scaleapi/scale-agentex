from enum import Enum
from typing import Annotated, Literal, assert_never

from pydantic import BaseModel, Field

from src.api.schemas.task_message_updates import (
    DataDelta,
    ReasoningContentDelta,
    ReasoningSummaryDelta,
    StreamTaskMessageDelta,
    StreamTaskMessageDone,
    StreamTaskMessageFull,
    StreamTaskMessageStart,
    TaskMessageDelta,
    TaskMessageUpdate,
    TextDelta,
    ToolRequestDelta,
    ToolResponseDelta,
)
from src.domain.entities.task_messages import (
    TaskMessageContentEntity,
    TaskMessageEntity,
    convert_task_message_content_to_entity,
    convert_task_message_to_entity,
)


class DeltaType(str, Enum):
    TEXT = "text"
    DATA = "data"
    TOOL_REQUEST = "tool_request"
    TOOL_RESPONSE = "tool_response"
    REASONING_SUMMARY = "reasoning_summary"
    REASONING_CONTENT = "reasoning_content"


class BaseTaskMessageDeltaEntity(BaseModel):
    """Base class for all delta updates"""

    type: DeltaType


class TextDeltaEntity(BaseTaskMessageDeltaEntity):
    """Delta for text updates"""

    type: Literal[DeltaType.TEXT] = DeltaType.TEXT
    text_delta: str | None = ""


def convert_text_delta_to_entity(delta: TextDelta) -> TextDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return TextDeltaEntity(text_delta=delta.text_delta)


class DataDeltaEntity(BaseTaskMessageDeltaEntity):
    """Delta for data updates"""

    type: Literal[DeltaType.DATA] = DeltaType.DATA
    data_delta: str | None = ""


def convert_data_delta_to_entity(delta: DataDelta) -> DataDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return DataDeltaEntity(data_delta=delta.data_delta)


class ToolRequestDeltaEntity(BaseTaskMessageDeltaEntity):
    """Delta for tool request updates"""

    type: Literal[DeltaType.TOOL_REQUEST] = DeltaType.TOOL_REQUEST
    tool_call_id: str
    name: str
    arguments_delta: str | None = ""


def convert_tool_request_delta_to_entity(
    delta: ToolRequestDelta,
) -> ToolRequestDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return ToolRequestDeltaEntity(
        tool_call_id=delta.tool_call_id,
        name=delta.name,
        arguments_delta=delta.arguments_delta,
    )


class ToolResponseDeltaEntity(BaseTaskMessageDeltaEntity):
    """Delta for tool response updates"""

    type: Literal[DeltaType.TOOL_RESPONSE] = DeltaType.TOOL_RESPONSE
    tool_call_id: str
    name: str
    content_delta: str | None = ""


def convert_tool_response_delta_to_entity(
    delta: ToolResponseDelta,
) -> ToolResponseDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return ToolResponseDeltaEntity(
        tool_call_id=delta.tool_call_id,
        name=delta.name,
        content_delta=delta.content_delta,
    )


class ReasoningSummaryDeltaEntity(BaseTaskMessageDeltaEntity):
    """Delta for reasoning summary updates"""

    type: Literal[DeltaType.REASONING_SUMMARY] = DeltaType.REASONING_SUMMARY
    summary_index: int
    summary_delta: str | None = ""


def convert_reasoning_summary_delta_to_entity(
    delta: ReasoningSummaryDelta,
) -> ReasoningSummaryDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return ReasoningSummaryDeltaEntity(
        summary_index=delta.summary_index,
        summary_delta=delta.summary_delta,
    )


class ReasoningContentDeltaEntity(BaseTaskMessageDeltaEntity):
    """Delta for reasoning content updates"""

    type: Literal[DeltaType.REASONING_CONTENT] = DeltaType.REASONING_CONTENT
    content_index: int
    content_delta: str | None = ""


def convert_reasoning_content_delta_to_entity(
    delta: ReasoningContentDelta,
) -> ReasoningContentDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return ReasoningContentDeltaEntity(
        content_index=delta.content_index,
        content_delta=delta.content_delta,
    )


TaskMessageDeltaEntity = Annotated[
    TextDeltaEntity
    | DataDeltaEntity
    | ToolRequestDeltaEntity
    | ToolResponseDeltaEntity
    | ReasoningSummaryDeltaEntity
    | ReasoningContentDeltaEntity,
    Field(discriminator="type"),
]


def convert_task_message_delta_to_entity(
    delta: TaskMessageDelta,
) -> TaskMessageDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    if isinstance(delta.root, TextDelta):
        return convert_text_delta_to_entity(delta.root)
    if isinstance(delta.root, DataDelta):
        return convert_data_delta_to_entity(delta.root)
    if isinstance(delta.root, ToolRequestDelta):
        return convert_tool_request_delta_to_entity(delta.root)
    if isinstance(delta.root, ToolResponseDelta):
        return convert_tool_response_delta_to_entity(delta.root)
    if isinstance(delta.root, ReasoningSummaryDelta):
        return convert_reasoning_summary_delta_to_entity(delta.root)
    if isinstance(delta.root, ReasoningContentDelta):
        return convert_reasoning_content_delta_to_entity(delta.root)

    assert_never(delta.root)


class TaskMessageUpdateType(str, Enum):
    START = "start"
    FULL = "full"
    DELTA = "delta"
    DONE = "done"


class StreamTaskMessageEntity(BaseModel):
    """Base class for all task message stream events"""

    type: TaskMessageUpdateType
    index: int | None = None
    # Used for streaming chunks to a direct parent_task_message
    parent_task_message: TaskMessageEntity | None = None


class StreamTaskMessageStartEntity(StreamTaskMessageEntity):
    """Event for starting a streaming message"""

    type: Literal[TaskMessageUpdateType.START] = TaskMessageUpdateType.START
    content: TaskMessageContentEntity


def convert_stream_task_message_start_to_entity(
    message: StreamTaskMessageStart,
) -> StreamTaskMessageStartEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return StreamTaskMessageStartEntity(
        index=message.index,
        parent_task_message=convert_task_message_to_entity(message.parent_task_message)
        if message.parent_task_message
        else None,
        content=convert_task_message_content_to_entity(message.content.root),
    )


class StreamTaskMessageDeltaEntity(StreamTaskMessageEntity):
    """Event for streaming chunks of content"""

    type: Literal[TaskMessageUpdateType.DELTA] = TaskMessageUpdateType.DELTA
    delta: TaskMessageDeltaEntity | None = None


def convert_stream_task_message_delta_to_entity(
    message: StreamTaskMessageDelta,
) -> StreamTaskMessageDeltaEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    return StreamTaskMessageDeltaEntity(
        index=message.index,
        parent_task_message=convert_task_message_to_entity(message.parent_task_message)
        if message.parent_task_message
        else None,
        delta=convert_task_message_delta_to_entity(message.delta)
        if message.delta
        else None,
    )


class StreamTaskMessageFullEntity(StreamTaskMessageEntity):
    """Event for streaming the full content"""

    type: Literal[TaskMessageUpdateType.FULL] = TaskMessageUpdateType.FULL
    content: TaskMessageContentEntity


def convert_stream_task_message_full_to_entity(
    message: StreamTaskMessageFull,
) -> StreamTaskMessageFullEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    return StreamTaskMessageFullEntity(
        index=message.index,
        parent_task_message=convert_task_message_to_entity(message.parent_task_message)
        if message.parent_task_message
        else None,
        content=convert_task_message_content_to_entity(message.content.root),
    )


class StreamTaskMessageDoneEntity(StreamTaskMessageEntity):
    """Event for indicating the task is done"""

    type: Literal[TaskMessageUpdateType.DONE] = TaskMessageUpdateType.DONE


def convert_stream_task_message_done_to_entity(
    message: StreamTaskMessageDone,
) -> StreamTaskMessageDoneEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    return StreamTaskMessageDoneEntity(
        index=message.index,
        parent_task_message=convert_task_message_to_entity(message.parent_task_message)
        if message.parent_task_message
        else None,
    )


TaskMessageUpdateEntity = Annotated[
    StreamTaskMessageStartEntity
    | StreamTaskMessageDeltaEntity
    | StreamTaskMessageFullEntity
    | StreamTaskMessageDoneEntity,
    Field(discriminator="type"),
]


def convert_task_message_update_to_entity(
    message: TaskMessageUpdate,
) -> TaskMessageUpdateEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    if isinstance(message.root, StreamTaskMessageStart):
        return convert_stream_task_message_start_to_entity(message.root)
    if isinstance(message.root, StreamTaskMessageDelta):
        return convert_stream_task_message_delta_to_entity(message.root)
    if isinstance(message.root, StreamTaskMessageFull):
        return convert_stream_task_message_full_to_entity(message.root)
    if isinstance(message.root, StreamTaskMessageDone):
        return convert_stream_task_message_done_to_entity(message.root)

    assert_never(message.root)
