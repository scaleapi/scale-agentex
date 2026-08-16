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
    # Non-terminal resting state: the current turn was stopped by the user and the
    # task is waiting for the next message. Distinct from RUNNING (a turn is
    # actively in flight) and from the terminal statuses below.
    INTERRUPTED = "INTERRUPTED"
    TERMINATED = "TERMINATED"
    TIMED_OUT = "TIMED_OUT"
    DELETED = "DELETED"


# Canonical status partition (state machine + SSE termination).
# Non-terminal: RUNNING or INTERRUPTED (resumable); terminal is the rest.
# New statuses are terminal unless added to the non-terminal set.
NON_TERMINAL_TASK_STATUSES = frozenset({TaskStatus.RUNNING, TaskStatus.INTERRUPTED})
TERMINAL_TASK_STATUSES = frozenset(TaskStatus) - NON_TERMINAL_TASK_STATUSES


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
    cleaned_at: datetime | None = Field(
        None,
        title="The timestamp when the task's content was cleaned for retention compliance; null when active",
    )
    params: dict[str, Any] | None = Field(
        None,
        title="Task parameters",
    )
    task_metadata: dict[str, Any] | None = Field(
        None,
        title="Task metadata",
    )
    current_state: str | None = Field(
        None,
        title=(
            "Opaque label mirroring the agent's StateMachine current state; "
            "null when the agent does not emit one. Orthogonal to 'status'."
        ),
    )

    # allow extra fields for agents relationships
    model_config = ConfigDict(extra="allow")


def convert_task_to_entity(task: Task) -> TaskEntity:
    """Converts the pydantic model from the API layer to the domain layer"""
    return TaskEntity.model_validate(task)
