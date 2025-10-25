from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class TaskStatus(str, Enum):
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    TIMED_OUT = "TIMED_OUT"
    DELETED = "DELETED"


class Task(BaseModel):
    id: str = Field(
        ...,
        title="Unique Task ID",
    )
    name: str | None = Field(
        None,
        title="Unique name of the task",
    )
    status: TaskStatus | None = Field(
        None,
        title="The current status of the task",
    )
    status_reason: str | None = Field(
        None,
        title="The reason for the current task status",
    )
    created_at: datetime | None = Field(
        None,
        title="The timestamp when the task was created",
    )
    updated_at: datetime | None = Field(
        None,
        title="The timestamp when the task was last updated",
    )
    params: dict[str, Any] | None = Field(
        None,
        title="Task parameters",
    )
    task_metadata: dict[str, Any] | None = Field(
        None,
        title="Task metadata",
    )


class UpdateTaskRequest(BaseModel):
    task_metadata: dict[str, Any] | None = Field(
        None,
        title="If provided, replaces task_metadata with this value",
    )
