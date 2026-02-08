from datetime import datetime

from pydantic import Field

from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

logger = make_logger(__name__)


class AgentAPIKey(BaseModel):
    id: str = Field(..., description="The unique identifier of the agent API key.")
    agent_id: str = Field(..., description="The UUID of the agent")
    created_at: datetime = Field(..., description="When the agent API key was created")
    name: str | None = Field(..., description="The optional name of the agent API key.")
    api_key_type: AgentAPIKeyType = Field(
        ...,
        description="The type of the agent API key (either internal or external)",
    )


class CreateAPIKeyRequest(BaseModel):
    agent_id: str | None = Field(None, description="The UUID of the agent")
    agent_name: str | None = Field(
        None,
        description="The name of the agent - if not provided, the agent_id must be set.",
    )
    name: str = Field(
        ...,
        description="The name of the agent's API key.",
    )
    api_key_type: AgentAPIKeyType = Field(
        AgentAPIKeyType.EXTERNAL,
        description="The type of the agent API key (external by default).",
    )
    api_key: str | None = Field(
        None,
        description="Optionally provide the API key value - if not set, one will be generated.",
    )


class CreateAPIKeyResponse(BaseModel):
    id: str = Field(..., description="The unique identifier of the agent API key.")
    agent_id: str = Field(..., description="The UUID of the agent")
    created_at: datetime = Field(..., description="When the agent API key was created")
    name: str | None = Field(..., description="The optional name of the agent API key.")
    api_key_type: AgentAPIKeyType = Field(
        ...,
        description="The type of the created agent API key (external).",
    )
    api_key: str = Field(
        ...,
        description="The value of the newly created API key.",
    )
