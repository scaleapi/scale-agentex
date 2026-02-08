from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import ConfigDict, Field

from src.api.schemas.tasks import Task
from src.utils.model_utils import BaseModel


class TaskRelationships(str, Enum):
    """Task relationships that can be loaded"""

    AGENTS = "agents"


class TaskStatus(str, Enum):
    # note that there's a typo here
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    TIMED_OUT = "TIMED_OUT"
    DELETED = "DELETED"


class TaskEntity(BaseModel):
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

    # allow extra fields for agents relationships
    model_config = ConfigDict(extra="allow")


def convert_task_to_entity(task: Task) -> TaskEntity:
    """Converts the pydantic model from the API layer to the domain layer"""

    return TaskEntity(
        id=task.id,
        name=task.name,
        status=TaskStatus[task.status.value] if task.status is not None else None,
        status_reason=task.status_reason,
        created_at=task.created_at,
        updated_at=task.updated_at,
        params=task.params,
        task_metadata=task.task_metadata,
    )
