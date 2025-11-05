from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class AgentStatus(str, Enum):
    READY = "Ready"
    FAILED = "Failed"
    UNKNOWN = "Unknown"
    DELETED = "Deleted"
    UNHEALTHY = "Unhealthy"


class ACPType(str, Enum):
    SYNC = "sync"
    ASYNC = "async"

    AGENTIC = "agentic"  # deprecated: use ASYNC instead


class AgentRPCMethod(str, Enum):
    EVENT_SEND = "event/send"
    TASK_CREATE = "task/create"
    MESSAGE_SEND = "message/send"
    TASK_CANCEL = "task/cancel"


class AgentInputType(str, Enum):
    TEXT = "text"
    JSON = "json"


class Agent(BaseModel):
    id: str = Field(..., description="The unique identifier of the agent.")
    name: str = Field(..., description="The unique name of the agent.")
    description: str = Field(..., description="The description of the action.")
    status: AgentStatus = Field(
        AgentStatus.UNKNOWN,
        description="The status of the action, indicating if it's building, ready, failed, etc.",
    )
    acp_type: ACPType = Field(
        ...,
        description="The type of the ACP Server (Either sync or async)",
    )
    status_reason: str | None = Field(
        None, description="The reason for the status of the action."
    )
    created_at: datetime = Field(
        ..., description="The timestamp when the agent was created"
    )
    updated_at: datetime = Field(
        ..., description="The timestamp when the agent was last updated"
    )
    registration_metadata: dict[str, Any] | None = Field(
        default=None,
        description="The metadata for the agent's registration.",
    )
    registered_at: datetime | None = Field(
        default=None,
        description="The timestamp when the agent was last registered",
    )
    agent_input_type: AgentInputType | None = Field(
        default=None, description="The type of input the agent expects."
    )

    class Config:
        orm_mode = True


class RegisterAgentRequest(BaseModel):
    name: str = Field(
        ..., pattern=r"^[a-z0-9-]+$", description="The unique name of the agent."
    )
    description: str = Field(..., description="The description of the agent.")
    acp_url: str = Field(..., description="The URL of the ACP server for the agent.")
    agent_id: str | None = Field(
        default=None,
        description="Optional agent ID if the agent already exists and needs to be updated.",
    )
    acp_type: ACPType = Field(..., description="The type of ACP to use for the agent.")
    principal_context: Any | None = Field(
        default=None, description="Principal used for authorization"
    )
    registration_metadata: dict[str, Any] | None = Field(
        default=None,
        description="The metadata for the agent's registration.",
    )
    agent_input_type: AgentInputType | None = Field(
        default=None, description="The type of input the agent expects."
    )


class RegisterAgentResponse(Agent):
    """Response model for registering an agent."""

    agent_api_key: str | None = Field(
        None, description="The API key for the agent, if applicable."
    )
