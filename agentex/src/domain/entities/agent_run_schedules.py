from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.domain.entities.agents import ACPType
from src.utils.model_utils import BaseModel


class InitialInputMethod(str, Enum):
    """How the configured first input is delivered to the freshly created task.

    Always inferred from the target agent's ACP type at fire time.
    """

    EVENT_SEND = "event/send"  # async / agentic agents
    MESSAGE_SEND = "message/send"  # sync agents


def infer_initial_input_method(acp_type: ACPType) -> InitialInputMethod:
    """Map an agent's ACP type to the delivery method for the initial input.

    async / agentic agents receive the first input as an ``event/send``; sync
    agents receive it as a ``message/send``.
    """
    if acp_type == ACPType.SYNC:
        return InitialInputMethod.MESSAGE_SEND
    return InitialInputMethod.EVENT_SEND


class AgentRunScheduleEntity(BaseModel):
    """A persisted definition of a recurring agent run.

    The Postgres row is the source of truth for what each future fire should do;
    the Temporal Schedule is only the recurring clock and carries nothing but the
    schedule id.

    JSON-backed fields (``creator_principal``, ``task_params``, ``task_metadata``,
    ``initial_input``) are stored as plain dicts so they round-trip cleanly through
    the JSON columns. Their typed shapes are validated at the API schema layer
    (``ScheduleCreatorPrincipal`` / ``ScheduleInitialInput``).
    """

    id: str = Field(..., description="The unique identifier of the run schedule.")
    agent_id: str = Field(..., description="The agent this schedule belongs to.")
    name: str = Field(
        ..., description="Human-readable schedule name, unique per agent."
    )
    description: str | None = Field(
        None, description="Optional description of the schedule."
    )
    cron_expression: str | None = Field(
        None, description="Cron expression for the cadence (mutually exclusive)."
    )
    interval_seconds: int | None = Field(
        None, description="Interval cadence in seconds (mutually exclusive)."
    )
    timezone: str = Field(
        "UTC", description="IANA timezone the cron expression is evaluated in."
    )
    start_at: datetime | None = Field(
        None, description="When the schedule should start being active."
    )
    end_at: datetime | None = Field(
        None, description="When the schedule should stop being active."
    )
    paused: bool = Field(False, description="Whether the schedule is currently paused.")
    # Credential-free creator context: principal_type / user_id / service_account_id /
    # account_id only. Never cookies, JWTs, API keys, OAuth tokens, or headers.
    creator_principal: dict[str, Any] = Field(
        ...,
        description="Credential-free creator identity used for AuthZ at fire time.",
    )
    task_params: dict[str, Any] | None = Field(
        None, description="Resolved config forwarded as task `params` at fire time."
    )
    task_metadata: dict[str, Any] | None = Field(
        None, description="Metadata copied onto each created task at fire time."
    )
    initial_input: dict[str, Any] = Field(
        ..., description="The first input delivered to each created task."
    )
    created_at: datetime | None = Field(
        None, description="When the schedule was created."
    )
    updated_at: datetime | None = Field(
        None, description="When the schedule was last updated."
    )
    deleted_at: datetime | None = Field(
        None,
        description="When the schedule was soft-deleted (None while active).",
    )
    version: int = Field(
        1,
        description=(
            "Monotonic record version reserved for future optimistic concurrency "
            "control / change history. Not enforced yet."
        ),
    )
