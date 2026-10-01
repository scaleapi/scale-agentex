from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.api.schemas.agents import Agent
from src.utils.model_utils import BaseModel
from src.utils.task_constants import CURRENT_STATE_DESCRIPTION, CURRENT_STATE_MAX_LENGTH


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


class _TaskBase(BaseModel):
    """Shared fields for Task and TaskSummary (everything except `params`)."""

    id: str = Field(..., title="Unique Task ID")
    name: str | None = Field(None, title="Unique name of the task")
    status: TaskStatus | None = Field(None, title="The current status of the task")
    status_reason: str | None = Field(None, title="The reason for the current task status")
    created_at: datetime | None = Field(None, title="The timestamp when the task was created")
    updated_at: datetime | None = Field(None, title="The timestamp when the task was last updated")
    cleaned_at: datetime | None = Field(
        None,
        title="The timestamp when the task's content was cleaned for retention compliance; null when active",
    )
    task_metadata: dict[str, Any] | None = Field(None, title="Task metadata")
    # Writes are bounded; reads are not, so widening the column won't 500.
    current_state: str | None = Field(None, title=CURRENT_STATE_DESCRIPTION)


class Task(_TaskBase):
    params: dict[str, Any] | None = Field(None, title="Task parameters")


class TaskResponse(Task):
    """Task response model with optional related data based on relationships"""

    agents: list["Agent"] | None = Field(
        default=None,
        title="Agents associated with this task (only populated when 'agent' view is requested)",
    )


class TaskSummary(_TaskBase):
    """Lean list-response shape. Omits `params` (the arbitrary create-time
    payload, which can carry per-caller secrets and PII); fetch GET /tasks/{id}
    for the full record."""

    agents: list["Agent"] | None = Field(
        default=None,
        title="Agents associated with this task (only populated when 'agents' view is requested)",
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
            "If provided, replaces the task's current_state label. Omit to leave it "
            'untouched; send "" to clear it back to null (how an operator recovers a '
            "task whose agent died mid-state)."
        ),
    )


class TaskStatusReasonRequest(BaseModel):
    reason: str | None = Field(
        None,
        title="Optional reason for the status change",
    )
