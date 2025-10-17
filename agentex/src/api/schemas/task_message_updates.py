from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from src.api.schemas.task_messages import TaskMessage, TaskMessageContent


class DeltaType(str, Enum):
    TEXT = "text"
    DATA = "data"
    TOOL_REQUEST = "tool_request"
    TOOL_RESPONSE = "tool_response"
    REASONING_SUMMARY = "reasoning_summary"
    REASONING_CONTENT = "reasoning_content"


class BaseTaskMessageDelta(BaseModel):
    """Base class for all delta updates"""

    type: DeltaType


class TextDelta(BaseTaskMessageDelta):
    """Delta for text updates"""

    type: Literal[DeltaType.TEXT] = DeltaType.TEXT
    text_delta: str | None = ""


class DataDelta(BaseTaskMessageDelta):
    """Delta for data updates"""

    type: Literal[DeltaType.DATA] = DeltaType.DATA
    data_delta: str | None = ""


class ToolRequestDelta(BaseTaskMessageDelta):
    """Delta for tool request updates"""

    type: Literal[DeltaType.TOOL_REQUEST] = DeltaType.TOOL_REQUEST
    tool_call_id: str
    name: str
    arguments_delta: str | None = ""


class ToolResponseDelta(BaseTaskMessageDelta):
    """Delta for tool response updates"""

    type: Literal[DeltaType.TOOL_RESPONSE] = DeltaType.TOOL_RESPONSE
    tool_call_id: str
    name: str
    content_delta: str | None = ""


class ReasoningSummaryDelta(BaseTaskMessageDelta):
    """Delta for reasoning summary updates"""

    type: Literal[DeltaType.REASONING_SUMMARY] = DeltaType.REASONING_SUMMARY
    summary_index: int
    summary_delta: str | None = ""


class ReasoningContentDelta(BaseTaskMessageDelta):
    """Delta for reasoning content updates"""

    type: Literal[DeltaType.REASONING_CONTENT] = DeltaType.REASONING_CONTENT
    content_index: int
    content_delta: str | None = ""


class TaskMessageDelta(RootModel):
    root: Annotated[
        TextDelta
        | DataDelta
        | ToolRequestDelta
        | ToolResponseDelta
        | ReasoningSummaryDelta
        | ReasoningContentDelta,
        Field(discriminator="type"),
    ]


class TaskMessageUpdateType(str, Enum):
    START = "start"
    FULL = "full"
    DELTA = "delta"
    DONE = "done"


class StreamTaskMessage(BaseModel):
    """Base class for all task message stream events"""

    type: TaskMessageUpdateType
    index: int | None = None
    # Used for streaming chunks to a direct parent_task_message
    parent_task_message: TaskMessage | None = None


class StreamTaskMessageStart(StreamTaskMessage):
    """Event for starting a streaming message"""

    type: Literal[TaskMessageUpdateType.START] = TaskMessageUpdateType.START
    content: TaskMessageContent


class StreamTaskMessageDelta(StreamTaskMessage):
    """Event for streaming chunks of content"""

    type: Literal[TaskMessageUpdateType.DELTA] = TaskMessageUpdateType.DELTA
    delta: TaskMessageDelta | None = None


class StreamTaskMessageFull(StreamTaskMessage):
    """Event for streaming the full content"""

    type: Literal[TaskMessageUpdateType.FULL] = TaskMessageUpdateType.FULL
    content: TaskMessageContent


class StreamTaskMessageDone(StreamTaskMessage):
    """Event for indicating the task is done"""

    type: Literal[TaskMessageUpdateType.DONE] = TaskMessageUpdateType.DONE


class TaskMessageUpdate(RootModel):
    root: Annotated[
        StreamTaskMessageStart
        | StreamTaskMessageDelta
        | StreamTaskMessageFull
        | StreamTaskMessageDone,
        Field(discriminator="type"),
    ]
