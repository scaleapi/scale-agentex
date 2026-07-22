from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.api.schemas.agents import Agent
from src.utils.model_utils import BaseModel

# Upper bound on the opaque `current_state` label. Kept in sync with the
# `TaskORM.current_state` column width (String(255)); a state label is short and
# the value rides every task_updated SSE payload, so it is capped.
CURRENT_STATE_MAX_LENGTH = 255


class TaskRelationships(str, Enum):
    """Task relationships that can be loaded"""

    AGENTS = "agents"


class TaskStatus(str, Enum):
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    # Non-terminal: current turn stopped by the user, task still continuable.
    INTERRUPTED = "INTERRUPTED"
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
        max_length=CURRENT_STATE_MAX_LENGTH,
        title=(
            "Opaque label mirroring the agent's StateMachine current state; "
            "null when the agent does not emit one. Orthogonal to 'status'."
        ),
    )


class TaskResponse(Task):
    """Task response model with optional related data based on relationships"""

    agents: list["Agent"] | None = Field(
        default=None,
        title="Agents associated with this task (only populated when 'agent' view is requested)",
    )


class UpdateTaskRequest(BaseModel):
    task_metadata: dict[str, Any] | None = Field(
        None,
        title="If provided, replaces task_metadata with this value",
    )
    merge_params: dict[str, Any] | None = Field(
        None,
        title=(
            "Optional shallow-merge patch applied to the task's params column. "
            "Top-level keys overwrite; pass full nested objects to change "
            "subfields."
        ),
    )
    current_state: str | None = Field(
        None,
        max_length=CURRENT_STATE_MAX_LENGTH,
        title=(
            "If provided, replaces the task's current_state label; "
            "pass null to clear it, omit to leave it unchanged."
        ),
    )


class TaskStatusReasonRequest(BaseModel):
    reason: str | None = Field(
        None,
        title="Optional reason for the status change",
    )
