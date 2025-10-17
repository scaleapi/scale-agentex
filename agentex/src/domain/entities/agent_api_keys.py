from datetime import datetime
from enum import Enum

from pydantic import Field

from src.utils.model_utils import BaseModel


class AgentAPIKeyType(str, Enum):
    INTERNAL = "internal"  # Used for ACP <> Server communication
    EXTERNAL = "external"  # Used for API keys provided via x-agent-api-key header
    GITHUB = "github"  # Used for verifying signature in GitHub webhook requests
    SLACK = "slack"  # Used for verifying signature in Slack webhook requests


class AgentAPIKeyEntity(BaseModel):
    id: str = Field(..., description="The unique identifier of the API key.")
    agent_id: str = Field(..., description="The UUID of the agent")
    created_at: datetime | None = Field(
        None, description="When the API key was created"
    )
    name: str | None = Field(None, description="The optional name of the API key.")
    api_key_type: AgentAPIKeyType = Field(
        ...,
        description="The type of the API key (either internal or external)",
    )
    api_key: str = Field(..., description="The API key")
