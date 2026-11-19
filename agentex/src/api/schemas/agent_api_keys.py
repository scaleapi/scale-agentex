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


class CreateWebhookTriggerRequest(BaseModel):
    """One-call setup for a webhook trigger: register the source's signature key and
    get back the ready-to-paste forward webhook URL."""

    agent_name: str = Field(..., description="The agent the webhook drives.")
    source: AgentAPIKeyType = Field(
        AgentAPIKeyType.GITHUB,
        description="Webhook source whose signature is verified (github, slack or linear).",
    )
    name: str = Field(
        ...,
        description="Signature-lookup key: the repo full_name (github), api_app_id "
        "(slack) or OAuth client id (linear) that the forward ingress matches the incoming "
        "webhook against.",
    )
    forward_path: str = Field(
        ...,
        description="Subpath the agent's own route handles, e.g. 'github-pr/<config-id>'. "
        "Appended to /agents/forward/name/{agent_name}/ to form the webhook URL.",
    )
    secret: str | None = Field(
        None,
        description=(
            "Signing secret. For GitHub, omit to generate one, or provide an existing "
            "webhook secret. For Slack, this is required and must be the Slack app's "
            "Signing Secret. For Linear, this is required and must be the Linear OAuth "
            "app's webhook signing secret."
        ),
    )
    app_token: str | None = Field(
        None,
        description=(
            "Slack only. The app's app-level token (xapp-..., scope connections:write). "
            "When set, agentex receives the app's events over Socket Mode and forwards "
            "them to forward_path, so the app needs no public Request URL. Stored "
            "encrypted and never returned."
        ),
    )
    base_url: str | None = Field(
        None,
        description="Optional public agentex base URL for the returned webhook_url; "
        "defaults to the AGENTEX_PUBLIC_URL env var.",
    )


class CreateWebhookTriggerResponse(BaseModel):
    key_id: str = Field(..., description="The created agent API key id.")
    agent_name: str = Field(..., description="The agent the webhook drives.")
    source: AgentAPIKeyType = Field(
        ..., description="Webhook source (github or slack)."
    )
    name: str = Field(
        ..., description="Signature-lookup key (repo full_name / api_app_id)."
    )
    secret: str = Field(
        ...,
        description="The signing secret — shown once; paste into the source's webhook config.",
    )
    webhook_path: str = Field(..., description="The forward path to POST webhooks to.")
    webhook_url: str | None = Field(
        None,
        description="Full webhook URL to paste into the source (None if no base URL configured).",
    )


class SetSlackSocketModeRequest(BaseModel):
    """Turn Socket Mode on for an existing Slack trigger, or replace its settings."""

    app_token: str = Field(
        ...,
        description="The Slack app's app-level token (xapp-..., scope "
        "connections:write). It must belong to the app the trigger is named for. "
        "Stored encrypted and never returned.",
    )
    forward_path: str = Field(
        ...,
        description="Subpath of the agent each event is POSTed to, e.g. 'slack/events'.",
    )


class SlackSocketMode(BaseModel):
    key_id: str = Field(..., description="The Slack trigger's agent API key id.")
    slack_app_id: str = Field(..., description="The Slack app served over Socket Mode.")
    forward_path: str = Field(
        ..., description="Subpath of the agent each event is POSTed to."
    )
