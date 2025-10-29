from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.api.schemas.agents import Agent
from src.utils.model_utils import BaseModel


class TaskRelationships(str, Enum):
    """Task relationships that can be loaded"""

    AGENTS = "agents"


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
