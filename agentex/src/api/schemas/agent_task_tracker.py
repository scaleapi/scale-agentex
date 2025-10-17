from datetime import datetime

from pydantic import Field

from src.utils.model_utils import BaseModel


class UpdateAgentTaskTrackerRequest(BaseModel):
    """Request model for updating an agent task tracker."""

    last_processed_event_id: str | None = Field(
        None,
        description="The most recent processed event ID (omit to leave unchanged)",
    )
    status: str | None = Field(None, description="Processing status")
    status_reason: str | None = Field(None, description="Optional status reason")


class AgentTaskTracker(BaseModel):
    id: str = Field(..., description="The UUID of the agent task tracker")
    agent_id: str = Field(..., description="The UUID of the agent")
    task_id: str = Field(..., description="The UUID of the task")
    status: str | None = Field(None, description="Processing status")
    status_reason: str | None = Field(None, description="Optional status reason")
    last_processed_event_id: str | None = Field(
        None, description="The last processed event ID"
    )
    created_at: datetime = Field(
        ..., description="When the agent task tracker was created"
    )
    updated_at: datetime | None = Field(
        None, description="When the agent task tracker was last updated"
    )
