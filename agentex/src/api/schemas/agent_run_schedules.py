from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from src.domain.entities.task_messages import MessageAuthor
from src.utils.model_utils import BaseModel


class RunScheduleState(str, Enum):
    """Live state of a run schedule, derived from Temporal."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class ScheduleInitialInput(BaseModel):
    """The first input delivered to each freshly created scheduled task."""

    type: Literal["text"] = Field("text", description="Input content type.")
    author: MessageAuthor = Field(
        MessageAuthor.USER, description="The author attributed to the initial input."
    )
    content: str = Field(..., description="The initial prompt delivered to the task.")


class ScheduleCreatorPrincipal(BaseModel):
    """Credential-free creator identity stored with the schedule.

    Never carries cookies, JWTs, API keys, OAuth tokens, or request headers — it
    is creator *context* used only for AuthZ and ownership at fire time.
    """

    principal_type: str | None = Field(
        None, description="e.g. 'user' or 'service_account'."
    )
    user_id: str | None = Field(
        None, description="Creator user id, if a user principal."
    )
    service_account_id: str | None = Field(
        None, description="Creator service-account id, if a service principal."
    )
    account_id: str | None = Field(
        None, description="Account/workspace id of the creator."
    )


class CreateAgentRunScheduleRequest(BaseModel):
    """Request body for creating a scheduled agent run."""

    name: str = Field(
        ...,
        title="Schedule Name",
        description="Human-readable name, unique among active schedules for the agent.",
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        min_length=1,
        max_length=64,
    )
    description: str | None = Field(
        None, description="Optional description of what this schedule does."
    )
    cron_expression: str | None = Field(
        None,
        description="Cron expression for the cadence (e.g. '0 17 * * MON-FRI'). "
        "Mutually exclusive with interval_seconds.",
    )
    interval_seconds: int | None = Field(
        None,
        ge=1,
        description="Interval cadence in seconds. Mutually exclusive with cron_expression.",
    )
    timezone: str = Field(
        "UTC",
        description="IANA timezone the cron expression is evaluated in (e.g. 'America/New_York').",
    )
    start_at: datetime | None = Field(
        None, description="When the schedule should start being active."
    )
    end_at: datetime | None = Field(
        None, description="When the schedule should stop being active."
    )
    paused: bool = Field(
        False, description="Whether to create the schedule in a paused state."
    )
    task_params: dict[str, Any] | None = Field(
        None, description="Resolved config forwarded as task `params` at fire time."
    )
    task_metadata: dict[str, Any] | None = Field(
        None, description="Metadata copied onto each created task at fire time."
    )
    initial_input: ScheduleInitialInput = Field(
        ..., description="The first input delivered to each created task."
    )

    @model_validator(mode="after")
    def validate_single_cadence(self):
        # Exactly one cadence is required at create time. Rejecting both here
        # prevents a ScheduleSpec with both a cron and an interval (which would
        # fire on both); rejecting neither prevents a cadence-less schedule.
        if (self.cron_expression is None) == (self.interval_seconds is None):
            raise ValueError(
                "Provide exactly one of cron_expression or interval_seconds"
            )
        return self


class AgentRunScheduleResponse(BaseModel):
    """Response model describing a scheduled agent run."""

    id: str = Field(..., description="The unique identifier of the run schedule.")
    agent_id: str = Field(..., description="The agent this schedule belongs to.")
    name: str = Field(..., description="Human-readable schedule name.")
    description: str | None = Field(None, description="Optional description.")
    cron_expression: str | None = Field(
        None, description="Cron cadence, if cron-based."
    )
    interval_seconds: int | None = Field(
        None, description="Interval cadence in seconds, if interval-based."
    )
    timezone: str = Field(
        "UTC", description="Timezone the cron expression is evaluated in."
    )
    start_at: datetime | None = Field(None, description="Schedule activation time.")
    end_at: datetime | None = Field(None, description="Schedule deactivation time.")
    paused: bool = Field(False, description="Whether the schedule is paused.")
    task_params: dict[str, Any] | None = Field(
        None, description="Task params at fire time."
    )
    task_metadata: dict[str, Any] | None = Field(
        None, description="Task metadata at fire time."
    )
    initial_input: ScheduleInitialInput = Field(..., description="The initial input.")
    initial_input_method: str = Field(
        ...,
        description="Delivery method, inferred from the agent's ACP type.",
    )
    creator_principal: ScheduleCreatorPrincipal | None = Field(
        None, description="Credential-free creator identity."
    )
    created_at: datetime | None = Field(
        None, description="When the schedule was created."
    )
    updated_at: datetime | None = Field(
        None, description="When the schedule was updated."
    )
    # Live state derived from Temporal (best-effort; may be absent right after creation).
    state: RunScheduleState = Field(
        RunScheduleState.ACTIVE, description="Live schedule state from Temporal."
    )
    next_action_times: list[datetime] = Field(
        default_factory=list, description="Upcoming scheduled fire times."
    )
    live_data_available: bool | None = Field(
        None,
        description=(
            "Whether requested live Temporal fields were retrieved successfully. "
            "Null when live enrichment was not requested."
        ),
    )
    skipped_action_times: list[datetime] = Field(
        default_factory=list, description="Skipped one-off scheduled fire times."
    )
    last_action_time: datetime | None = Field(
        None, description="When the schedule last fired."
    )
    num_actions_taken: int = Field(
        0, description="Number of times the schedule has fired."
    )


class AgentRunScheduleListResponse(BaseModel):
    """Response model for listing run schedules."""

    run_schedules: list[AgentRunScheduleResponse] = Field(
        ..., description="The list of run schedules."
    )
    total: int = Field(..., description="The number of run schedules returned.")


class UpdateAgentRunScheduleRequest(BaseModel):
    """Partial update for a scheduled agent run.

    Only fields present in the request body are changed. Setting
    ``cron_expression`` clears ``interval_seconds`` and vice versa; providing both
    is rejected.
    """

    name: str | None = Field(
        None,
        title="Schedule Name",
        description="Human-readable name, unique among active schedules for the agent.",
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        min_length=1,
        max_length=64,
    )
    description: str | None = Field(
        None, description="Optional description of what this schedule does."
    )
    cron_expression: str | None = Field(
        None,
        description="New cron cadence. Mutually exclusive with interval_seconds.",
    )
    interval_seconds: int | None = Field(
        None,
        ge=1,
        description="New interval cadence in seconds. Mutually exclusive with cron_expression.",
    )
    timezone: str | None = Field(
        None, description="IANA timezone the cron expression is evaluated in."
    )
    start_at: datetime | None = Field(
        None, description="When the schedule should start being active."
    )
    end_at: datetime | None = Field(
        None, description="When the schedule should stop being active."
    )
    paused: bool | None = Field(
        None, description="Pause/resume the schedule as part of the update."
    )
    task_params: dict[str, Any] | None = Field(
        None, description="Resolved config forwarded as task `params` at fire time."
    )
    task_metadata: dict[str, Any] | None = Field(
        None, description="Metadata copied onto each created task at fire time."
    )
    initial_input: ScheduleInitialInput | None = Field(
        None, description="Replacement initial input delivered to each created task."
    )

    @model_validator(mode="after")
    def reject_both_cadences(self):
        # Partial update: providing neither cadence is fine (other fields may be
        # changing), but providing both is rejected here so the apply loop can't
        # silently drop one and leave a misleading 200.
        if self.cron_expression is not None and self.interval_seconds is not None:
            raise ValueError(
                "Provide only one of cron_expression or interval_seconds, not both"
            )
        return self


class PauseRunScheduleRequest(BaseModel):
    note: str | None = Field(None, description="Optional note explaining the pause.")


class ResumeRunScheduleRequest(BaseModel):
    note: str | None = Field(None, description="Optional note explaining the resume.")


def _require_timezone(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information.")
    return value


class SkipRunScheduleRequest(BaseModel):
    scheduled_time: datetime = Field(
        ...,
        description="Specific scheduled fire time to skip.",
    )

    @model_validator(mode="after")
    def require_scheduled_time_timezone(self):
        self.scheduled_time = _require_timezone(self.scheduled_time, "scheduled_time")
        return self


class UnskipRunScheduleRequest(BaseModel):
    scheduled_time: datetime = Field(
        ..., description="Specific scheduled fire time to unskip."
    )

    @model_validator(mode="after")
    def require_scheduled_time_timezone(self):
        self.scheduled_time = _require_timezone(self.scheduled_time, "scheduled_time")
        return self
