from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class AgentStatus(str, Enum):
    PENDING = "Pending"
    BUILDING = "Building"
    READY = "Ready"
    FAILED = "Failed"
    UNKNOWN = "Unknown"


class ACPType(str, Enum):
    SYNC = "sync"
    AGENTIC = "agentic"


class AgentEntity(BaseModel):
    id: str = Field(..., description="The unique identifier of the agent.")
    docker_image: str | None = Field(
        None,
        description="The URI of the image associated with the action. Only set if the packaging method is `docker`.",
    )
    name: str = Field(..., description="The unique name of the agent.")
    description: str = Field(..., description="The description of the action.")
    acp_type: ACPType = Field(
        ACPType.AGENTIC,
        description="The type of the ACP Server (Either sync or agentic)",
    )
    status: AgentStatus = Field(
        AgentStatus.UNKNOWN,
        description="The status of the action, indicating if it's building, ready, failed, etc.",
    )
    status_reason: str | None = Field(
        None, description="The reason for the status of the action."
    )
    acp_url: str | None = Field(
        None,
        description="The URL of the agent's ACP server. This is set when the agent's service is deployed.",
    )
    created_at: datetime | None = Field(
        None, description="The timestamp when the agent was created"
    )
    updated_at: datetime | None = Field(
        None, description="The timestamp when the agent was last updated"
    )
    registration_metadata: dict[str, Any] | None = Field(
        None, description="The metadata for the agent's registration."
    )
    registered_at: datetime | None = Field(
        None, description="The timestamp when the agent was last registered"
    )
