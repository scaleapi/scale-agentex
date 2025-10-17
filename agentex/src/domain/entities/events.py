from datetime import datetime

from pydantic import Field

from src.domain.entities.task_messages import TaskMessageContentEntity
from src.utils.model_utils import BaseModel


class EventEntity(BaseModel):
    id: str = Field(..., description="The UUID of the event")
    sequence_id: int = Field(..., description="The sequence ID of the event")
    task_id: str = Field(
        ..., description="The UUID of the task that the event belongs to"
    )
    agent_id: str = Field(
        ..., description="The UUID of the agent that the event belongs to"
    )
    created_at: datetime | None = Field(None, description="The timestamp of the event")
    content: TaskMessageContentEntity | None = Field(
        None, description="The content of the event"
    )
