from datetime import datetime
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class CreateStateRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to send the state to",
    )
    agent_id: str = Field(
        ...,
        title="The unique id of the agent to send the state to",
    )
    state: dict[str, Any] = Field(
        ...,
        title="The state to send to the task.",
    )


class GetStatesRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to get the states from",
    )
    agent_id: str = Field(
        ...,
        title="The unique id of the agent to get the state from",
    )


class UpdateStateRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to update the state of",
    )
    agent_id: str = Field(
        ...,
        title="The unique id of the agent to update the state of",
    )
    state: dict[str, Any] = Field(
        ...,
        title="The state to update the state with.",
    )


class DeleteStateRequest(BaseModel):
    task_id: str = Field(
        ...,
        title="The unique id of the task to delete the state from",
    )
    agent_id: str = Field(
        ...,
        title="The unique id of the agent to delete the state from",
    )


class State(CreateStateRequest):
    """
    Represents a state in the agent system. A state is associated uniquely with a task and an agent.

    This entity is used to store states in MongoDB, with each state
    associated with a specific task and agent. The combination of task_id and agent_id is globally unique.

    The state is a dictionary of arbitrary data.
    """

    id: str = Field(..., description="The task state's unique id")
    created_at: datetime = Field(
        ..., description="The timestamp when the state was created"
    )
    updated_at: datetime | None = Field(
        None, description="The timestamp when the state was last updated"
    )
