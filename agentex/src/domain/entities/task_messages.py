from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, assert_never

from pydantic import Field

from src.api.schemas.task_messages import (
    DataContent,
    ReasoningContent,
    TaskMessage,
    TextContent,
    ToolRequestContent,
    ToolResponseContent,
)
from src.utils.model_utils import BaseModel, make_optional


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


class FileAttachmentEntity(BaseModel):
    """
    Represents a file attachment in messages.
    """

    file_id: str = Field(..., description="The unique ID of the attached file")
    name: str = Field(..., description="The name of the file")
    size: int = Field(..., description="The size of the file in bytes")
    type: str = Field(..., description="The MIME type or content type of the file")


class BaseTaskMessageContentEntity(BaseModel):
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


class TextContentEntity(BaseTaskMessageContentEntity):
    type: Literal[TaskMessageContentType.TEXT] = Field(
        default=TaskMessageContentType.TEXT,
        description="The type of the message, in this case `text`.",
    )
    format: TextFormat = Field(
        default=TextFormat.PLAIN,
        description="The format of the message. This is used by the client to determine how to display the message.",
    )
    content: str = Field(..., description="The contents of the text message.")
    attachments: list[FileAttachmentEntity] | None = Field(
        default=None,
        description="Optional list of file attachments with structured metadata.",
    )


OptionalTextContentEntity = make_optional(TextContentEntity)


class ReasoningContentEntity(BaseTaskMessageContentEntity):
    type: Literal[TaskMessageContentType.REASONING] = Field(
        default=TaskMessageContentType.REASONING,
        description="The type of the message, in this case `reasoning`.",
    )
    summary: list[str] = Field(..., description="A list of short reasoning summaries")
    content: list[str] | None = Field(
        None, description="The reasoning content or chain-of-thought text"
    )


OptionalReasoningContentEntity = make_optional(ReasoningContentEntity)


class ToolRequestContentEntity(BaseTaskMessageContentEntity):
    type: Literal[TaskMessageContentType.TOOL_REQUEST] = Field(
        default=TaskMessageContentType.TOOL_REQUEST,
        description="The type of the message, in this case `tool_request`.",
    )
    tool_call_id: str = Field(
        ..., description="The ID of the tool call that is being requested."
    )
    name: str = Field(..., description="The name of the tool that is being requested.")
    arguments: dict[str, Any] = Field(..., description="The arguments to the tool.")


OptionalToolRequestContentEntity = make_optional(ToolRequestContentEntity)


class ToolResponseContentEntity(BaseTaskMessageContentEntity):
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


OptionalToolResponseContentEntity = make_optional(ToolResponseContentEntity)


class DataContentEntity(BaseTaskMessageContentEntity):
    type: Literal[TaskMessageContentType.DATA] = Field(
        default=TaskMessageContentType.DATA,
        description="The type of the message, in this case `data`.",
    )
    data: dict[str, Any] = Field(..., description="The contents of the data message.")


OptionalDataContentEntity = make_optional(DataContentEntity)

TaskMessageContentEntity = Annotated[
    TextContentEntity
    | DataContentEntity
    | ToolRequestContentEntity
    | ToolResponseContentEntity
    | ReasoningContentEntity,
    Field(discriminator="type"),
]

OptionalTaskMessageContentEntity = (
    OptionalToolRequestContentEntity
    | OptionalDataContentEntity
    | OptionalTextContentEntity
    | OptionalToolResponseContentEntity
    | OptionalReasoningContentEntity
    | None
)


def convert_task_message_content_to_entity(
    content: TextContent
    | ReasoningContent
    | DataContent
    | ToolRequestContent
    | ToolResponseContent,
) -> TaskMessageContentEntity:
    if isinstance(content, TextContent):
        return TextContentEntity(
            author=content.author.value,
            style=content.style.value,
            format=content.format.value,
            content=content.content,
            attachments=[
                FileAttachmentEntity(**attachment.model_dump())
                for attachment in content.attachments
            ]
            if content.attachments
            else None,
        )
    if isinstance(content, ReasoningContent):
        return ReasoningContentEntity(
            author=content.author.value,
            style=content.style.value,
            summary=content.summary,
            content=content.content,
        )
    if isinstance(content, DataContent):
        return DataContentEntity(
            author=content.author.value,
            style=content.style.value,
            data=content.data,
        )
    if isinstance(content, ToolRequestContent):
        return ToolRequestContentEntity(
            author=content.author.value,
            style=content.style.value,
            tool_call_id=content.tool_call_id,
            name=content.name,
            arguments=content.arguments,
        )
    if isinstance(content, ToolResponseContent):
        return ToolResponseContentEntity(
            author=content.author.value,
            style=content.style.value,
            tool_call_id=content.tool_call_id,
            name=content.name,
            content=content.content,
        )

    assert_never(content)


class TaskMessageEntity(BaseModel):
    """
    Represents a message in the agent system.

    This entity is used to store messages in MongoDB, with each message
    associated with a specific task.
    """

    id: str | None = Field(None, description="The task message's unique id")
    task_id: str = Field(..., description="ID of the task this message belongs to")
    content: TaskMessageContentEntity = Field(
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


class TaskMessageEntityFilter(BaseModel):
    """Filter model for TaskMessage - all fields optional for flexible filtering."""

    content: OptionalTaskMessageContentEntity | None = Field(
        None, description="Filter by message content"
    )
    streaming_status: Literal["IN_PROGRESS", "DONE"] | None = Field(
        None, description="Filter by streaming status"
    )
    created_at: datetime | None = Field(
        None, description="Filter by message creation timestamp"
    )
    updated_at: datetime | None = Field(
        None, description="Filter by message last update timestamp"
    )


def convert_task_message_to_entity(message: TaskMessage) -> TaskMessageEntity:
    return TaskMessageEntity(
        id=message.id,
        task_id=message.task_id,
        content=convert_task_message_content_to_entity(message.content.root),
        streaming_status=message.streaming_status,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )
