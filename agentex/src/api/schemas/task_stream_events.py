from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from src.api.schemas.task_message_updates import (
    StreamTaskMessageDelta,
    StreamTaskMessageDone,
    StreamTaskMessageFull,
    StreamTaskMessageStart,
)
from src.api.schemas.tasks import Task


class TaskStreamConnectedEvent(BaseModel):
    """Issued when a stream is connected / initialized. This is not a task message update."""

    type: Literal["connected"]
    taskId: str
    """The task this stream is subscribed to."""


class TaskStreamErrorEvent(BaseModel):
    """Issued when a stream encounters an error. This is not a task message update."""

    type: Literal["error"]
    message: str
    """Error message"""


class TaskStreamTaskUpdatedEvent(BaseModel):
    """Issued when the task itself is meaningfully changed. This is not a task message update."""

    type: Literal["task_updated"]
    task: Task | None = None
    """
    The updated task.
    This is optional since I'm not sure if we will always want to send the task back inside this event.
    Perhaps we can change this to be required later.
    """


class TaskStreamEvent(RootModel):
    root: Annotated[
        StreamTaskMessageStart
        | StreamTaskMessageDelta
        | StreamTaskMessageFull
        | StreamTaskMessageDone
        | TaskStreamConnectedEvent
        | TaskStreamErrorEvent
        | TaskStreamTaskUpdatedEvent,
        Field(discriminator="type"),
    ]
