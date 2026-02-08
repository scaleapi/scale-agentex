from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import Field, RootModel

from src.utils.model_utils import BaseModel


class TaskMessageContentType(str, Enum):
    TEXT = "text"
    REASONING = "reasoning"
    DATA = "data"
    TOOL_REQUEST = "tool_request"
    TOOL_RESPONSE = "tool_response"


class MessageAuthor(str, Enum):
    USER = "user"
    AGENT = "agent"


class MessageStyle(str, Enum):
    STATIC = "static"
    ACTIVE = "active"


class TextFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAIN = "plain"
    CODE = "code"


class FileAttachment(BaseModel):
    """
    Represents a file attachment in messages.
    """

    file_id: str = Field(..., description="The unique ID of the attached file")
    name: str = Field(..., description="The name of the file")
    size: int = Field(..., description="The size of the file in bytes")
    type: str = Field(..., description="The MIME type or content type of the file")


class BaseTaskMessageContent(BaseModel):
    type: TaskMessageContentType = Field(
        ...,
        description="The type of the message, in this case `text`, `data`, `tool_request`, `tool_response`, or `tool_confirmation_request`.",
    )
    author: MessageAuthor = Field(
        ...,
        description="The role of the messages author, in this case `system`, `user`, `assistant`, or `tool`.",
    )
    style: MessageStyle = Field(
        default=MessageStyle.STATIC,
        description="The style of the message. This is used by the client to determine how to display the message.",
    )


class TextContent(BaseTaskMessageContent):
    type: Literal[TaskMessageContentType.TEXT] = Field(
        default=TaskMessageContentType.TEXT,
        description="The type of the message, in this case `text`.",
    )
    format: TextFormat = Field(
        default=TextFormat.PLAIN,
        description="The format of the message. This is used by the client to determine how to display the message.",
    )
    content: str = Field(..., description="The contents of the text message.")
    attachments: list[FileAttachment] | None = Field(
        default=None,
        description="Optional list of file attachments with structured metadata.",
    )


class ReasoningContent(BaseTaskMessageContent):
    type: Literal[TaskMessageContentType.REASONING] = Field(
        default=TaskMessageContentType.REASONING,
        description="The type of the message, in this case `reasoning`.",
    )
    summary: list[str] = Field(..., description="A list of short reasoning summaries")
    content: list[str] | None = Field(
        None, description="The reasoning content or chain-of-thought text"
    )


class ToolRequestContent(BaseTaskMessageContent):
    type: Literal[TaskMessageContentType.TOOL_REQUEST] = Field(
        default=TaskMessageContentType.TOOL_REQUEST,
        description="The type of the message, in this case `tool_request`.",
    )
    tool_call_id: str = Field(
        ..., description="The ID of the tool call that is being requested."
    )
    name: str = Field(..., description="The name of the tool that is being requested.")
    arguments: dict[str, Any] = Field(..., description="The arguments to the tool.")


class ToolResponseContent(BaseTaskMessageContent):
    type: Literal[TaskMessageContentType.TOOL_RESPONSE] = Field(
        default=TaskMessageContentType.TOOL_RESPONSE,
        description="The type of the message, in this case `tool_response`.",
    )
    tool_call_id: str = Field(
        ..., description="The ID of the tool call that is being responded to."
    )
    name: str = Field(
        ..., description="The name of the tool that is being responded to."
    )
    content: Any = Field(..., description="The result of the tool.")


class DataContent(BaseTaskMessageContent):
    type: Literal[TaskMessageContentType.DATA] = Field(
        default=TaskMessageContentType.DATA,
        description="The type of the message, in this case `data`.",
    )
    data: dict[str, Any] = Field(..., description="The contents of the data message.")


class TaskMessageContent(RootModel):
    root: Annotated[
        TextContent
        | ReasoningContent
        | DataContent
        | ToolRequestContent
        | ToolResponseContent,
        Field(discriminator="type"),
    ]


class CreateTaskMessageRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to send the message to",
    )
    content: TaskMessageContent = Field(
        ...,
        title="The message to send to the task.",
    )
    streaming_status: Literal["IN_PROGRESS", "DONE"] | None = Field(
        None,
        title="The streaming status of the message",
    )


class UpdateTaskMessageRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to update the message of",
    )
    content: TaskMessageContent = Field(
        ...,
        title="The message to update the message with.",
    )
    streaming_status: Literal["IN_PROGRESS", "DONE"] | None = Field(
        None,
        title="The streaming status of the message",
    )


class BatchCreateTaskMessagesRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to send the messages to",
    )
    contents: list[TaskMessageContent] = Field(
        ...,
        title="The messages to send to the task. The order of the messages will be the order they are added to the task.",
    )


class BatchUpdateTaskMessagesRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to update the messages of",
    )
    updates: dict[str, TaskMessageContent] = Field(
        ...,
        title="The updates to apply to the messages. The key is the TaskMessage id and the value is the TaskMessageContent to update the message with.",
    )


class TaskMessage(BaseModel):
    """
    Represents a message in the agent system.

    This entity is used to store messages in MongoDB, with each message
    associated with a specific task.
    """

    id: str | None = Field(None, description="The task message's unique id")
    task_id: str = Field(..., description="ID of the task this message belongs to")
    content: TaskMessageContent = Field(
        ...,
        description="The content of the message. This content is not OpenAI compatible. These are messages that are meant to be displayed to the user.",
    )
    streaming_status: Literal["IN_PROGRESS", "DONE"] | None = Field(
        None,
        title="In case of streaming, this indicates whether the message is still being streamed or has been completed",
    )
    created_at: datetime | None = Field(
        None, description="The timestamp when the message was created"
    )
    updated_at: datetime | None = Field(
        None, description="The timestamp when the message was last updated"
    )
