from typing import Annotated, Literal, assert_never

from pydantic import BaseModel, Field

from src.api.schemas.task_message_updates import (
    StreamTaskMessageDelta,
    StreamTaskMessageDone,
    StreamTaskMessageFull,
    StreamTaskMessageStart,
)
from src.api.schemas.task_stream_events import (
    TaskStreamConnectedEvent,
    TaskStreamErrorEvent,
    TaskStreamEvent,
    TaskStreamTaskUpdatedEvent,
)
from src.domain.entities.task_message_updates import (
    StreamTaskMessageDeltaEntity,
    StreamTaskMessageDoneEntity,
    StreamTaskMessageFullEntity,
    StreamTaskMessageStartEntity,
    convert_stream_task_message_delta_to_entity,
    convert_stream_task_message_done_to_entity,
    convert_stream_task_message_full_to_entity,
    convert_stream_task_message_start_to_entity,
)
from src.domain.entities.tasks import TaskEntity, convert_task_to_entity


class TaskStreamConnectedEventEntity(BaseModel):
    """Issued when a stream is connected / initialized. This is not a task message update."""

    type: Literal["connected"]
    taskId: str
    """The task this stream is subscribed to."""


def convert_task_stream_connect_event_to_entity(
    event: TaskStreamConnectedEvent,
) -> TaskStreamConnectedEventEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    return TaskStreamConnectedEventEntity(type="connected", taskId=event.taskId)


class TaskStreamErrorEventEntity(BaseModel):
    """Issued when a stream encounters an error. This is not a task message update."""

    type: Literal["error"]
    message: str
    """Error message"""


def convert_task_stream_error_event_to_entity(
    event: TaskStreamErrorEvent,
) -> TaskStreamErrorEventEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    return TaskStreamErrorEventEntity(type="error", message=event.message)


class TaskStreamTaskUpdatedEventEntity(BaseModel):
    """Issued when the task itself is meaningfully changed. This is not a task message update."""

    type: Literal["task_updated"]
    task: TaskEntity | None = None
    """
    The updated task.
    This is optional since I'm not sure if we will always want to send the task back inside this event.
    Perhaps we can change this to be required later.
    """


def convert_task_stream_task_updated_event_to_entity(
    event: TaskStreamTaskUpdatedEvent,
) -> TaskStreamTaskUpdatedEventEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return TaskStreamTaskUpdatedEventEntity(
        type="task_updated",
        task=convert_task_to_entity(event.task) if event.task is not None else None,
    )


TaskStreamEventEntity = Annotated[
    StreamTaskMessageStartEntity
    | StreamTaskMessageDeltaEntity
    | StreamTaskMessageFullEntity
    | StreamTaskMessageDoneEntity
    | TaskStreamConnectedEventEntity
    | TaskStreamErrorEventEntity
    | TaskStreamTaskUpdatedEventEntity,
    Field(discriminator="type"),
]


def convert_task_stream_event_to_entity(
    event: TaskStreamEvent,
) -> TaskStreamEventEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    if isinstance(event.root, StreamTaskMessageStart):
        return convert_stream_task_message_start_to_entity(event.root)
    if isinstance(event.root, StreamTaskMessageDelta):
        return convert_stream_task_message_delta_to_entity(event.root)
    if isinstance(event.root, StreamTaskMessageFull):
        return convert_stream_task_message_full_to_entity(event.root)
    if isinstance(event.root, StreamTaskMessageDone):
        return convert_stream_task_message_done_to_entity(event.root)
    if isinstance(event.root, TaskStreamConnectedEvent):
        return convert_task_stream_connect_event_to_entity(event.root)
    if isinstance(event.root, TaskStreamErrorEvent):
        return convert_task_stream_error_event_to_entity(event.root)
    if isinstance(event.root, TaskStreamTaskUpdatedEvent):
        return convert_task_stream_task_updated_event_to_entity(event.root)

    assert_never(event.root)
