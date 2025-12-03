from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class ScheduleState(str, Enum):
    """Schedule state enum"""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class CreateScheduleRequest(BaseModel):
    """Request model for creating a new schedule for an agent"""

    name: str = Field(
        ...,
        title="Schedule Name",
        description="Human-readable name for the schedule (e.g., 'weekly-profiling'). "
        "Will be combined with agent_id to form the full schedule_id.",
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        min_length=1,
        max_length=64,
    )
    workflow_name: str = Field(
        ...,
        title="Workflow Name",
        description="Name of the Temporal workflow to execute (e.g., 'sae-orchestrator')",
    )
    task_queue: str = Field(
        ...,
        title="Task Queue",
        description="Temporal task queue where the agent's worker is listening",
    )
    workflow_params: dict[str, Any] | None = Field(
        default=None,
        title="Workflow Parameters",
        description="Parameters to pass to the workflow",
    )
    cron_expression: str | None = Field(
        default=None,
        title="Cron Expression",
        description="Cron expression for scheduling (e.g., '0 0 * * 0' for weekly on Sunday)",
    )
    interval_seconds: int | None = Field(
        default=None,
        title="Interval Seconds",
        description="Alternative to cron - run every N seconds",
        ge=1,
    )
    execution_timeout_seconds: int | None = Field(
        default=None,
        title="Execution Timeout",
        description="Maximum time in seconds for each workflow execution",
        ge=1,
    )
    start_at: datetime | None = Field(
        default=None,
        title="Start At",
        description="When the schedule should start being active",
    )
    end_at: datetime | None = Field(
        default=None,
        title="End At",
        description="When the schedule should stop being active",
    )
    paused: bool = Field(
        default=False,
        title="Paused",
        description="Whether to create the schedule in a paused state",
    )


class ScheduleActionInfo(BaseModel):
    """Information about the scheduled action"""

    workflow_name: str = Field(
        ...,
        title="Workflow Name",
        description="Name of the workflow being executed",
    )
    workflow_id_prefix: str = Field(
        ...,
        title="Workflow ID Prefix",
        description="Prefix for workflow execution IDs",
    )
    task_queue: str = Field(
        ...,
        title="Task Queue",
        description="Task queue for the workflow",
    )
    workflow_params: list[Any] | None = Field(
        default=None,
        title="Workflow Parameters",
        description="Parameters passed to the workflow",
    )


class ScheduleSpecInfo(BaseModel):
    """Information about the schedule specification"""

    cron_expressions: list[str] = Field(
        default_factory=list,
        title="Cron Expressions",
        description="Cron expressions for the schedule",
    )
    intervals_seconds: list[int] = Field(
        default_factory=list,
        title="Interval Seconds",
        description="Interval specifications in seconds",
    )
    start_at: datetime | None = Field(
        default=None,
        title="Start At",
        description="When the schedule starts being active",
    )
    end_at: datetime | None = Field(
        default=None,
        title="End At",
        description="When the schedule stops being active",
    )


class ScheduleResponse(BaseModel):
    """Response model for schedule operations"""

    schedule_id: str = Field(
        ...,
        title="Schedule ID",
        description="Unique identifier for the schedule",
    )
    name: str = Field(
        ...,
        title="Schedule Name",
        description="Human-readable name for the schedule",
    )
    agent_id: str = Field(
        ...,
        title="Agent ID",
        description="ID of the agent this schedule belongs to",
    )
    state: ScheduleState = Field(
        ...,
        title="State",
        description="Current state of the schedule",
    )
    action: ScheduleActionInfo = Field(
        ...,
        title="Action",
        description="Information about the scheduled action",
    )
    spec: ScheduleSpecInfo = Field(
        ...,
        title="Spec",
        description="Schedule specification",
    )
    num_actions_taken: int = Field(
        default=0,
        title="Number of Actions Taken",
        description="Number of times the schedule has executed",
    )
    num_actions_missed: int = Field(
        default=0,
        title="Number of Actions Missed",
        description="Number of scheduled executions that were missed",
    )
    next_action_times: list[datetime] = Field(
        default_factory=list,
        title="Next Action Times",
        description="Upcoming scheduled execution times",
    )
    last_action_time: datetime | None = Field(
        default=None,
        title="Last Action Time",
        description="When the schedule last executed",
    )
    created_at: datetime | None = Field(
        default=None,
        title="Created At",
        description="When the schedule was created",
    )


class ScheduleListItem(BaseModel):
    """Abbreviated schedule info for list responses"""

    schedule_id: str = Field(
        ...,
        title="Schedule ID",
        description="Unique identifier for the schedule",
    )
    name: str = Field(
        ...,
        title="Schedule Name",
        description="Human-readable name for the schedule",
    )
    agent_id: str = Field(
        ...,
        title="Agent ID",
        description="ID of the agent this schedule belongs to",
    )
    state: ScheduleState = Field(
        ...,
        title="State",
        description="Current state of the schedule",
    )
    workflow_name: str | None = Field(
        default=None,
        title="Workflow Name",
        description="Name of the scheduled workflow",
    )
    next_action_time: datetime | None = Field(
        default=None,
        title="Next Action Time",
        description="Next scheduled execution time",
    )


class ScheduleListResponse(BaseModel):
    """Response model for listing schedules"""

    schedules: list[ScheduleListItem] = Field(
        ...,
        title="Schedules",
        description="List of schedules",
    )
    total: int = Field(
        ...,
        title="Total",
        description="Total number of schedules",
    )


class PauseScheduleRequest(BaseModel):
    """Request model for pausing a schedule"""

    note: str | None = Field(
        default=None,
        title="Note",
        description="Optional note explaining why the schedule was paused",
    )


class UnpauseScheduleRequest(BaseModel):
    """Request model for unpausing a schedule"""

    note: str | None = Field(
        default=None,
        title="Note",
        description="Optional note explaining why the schedule was unpaused",
    )
