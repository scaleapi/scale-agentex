from datetime import datetime
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class StateEntity(BaseModel):
    """
    Represents a state in the agent system. A state is associated uniquely with a task and an agent.

    This entity is used to store states in MongoDB, with each state
    associated with a specific task and agent. The combination of task_id and agent_id is globally unique.

    The state is a dictionary of arbitrary data.
    """

    id: str | None = Field(None, description="The task state's unique id")
    task_id: str = Field(
        description="ID of the task this state belongs to. The combination of task_id and agent_id is globally unique."
    )
    agent_id: str = Field(
        description="ID of the agent this state belongs to. The combination of task_id and agent_id is globally unique."
    )
    state: dict[str, Any] = Field(
        description="The state object that contains arbitrary data"
    )
    created_at: datetime | None = Field(
        None, description="The timestamp when the state was created"
    )
    updated_at: datetime | None = Field(
        None, description="The timestamp when the state was last updated"
    )
