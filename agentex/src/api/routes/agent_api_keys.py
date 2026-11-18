import os
import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.api.schemas.agent_api_keys import (
    AgentAPIKey,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    CreateWebhookTriggerRequest,
    CreateWebhookTriggerResponse,
    SetSlackSocketModeRequest,
    SlackSocketMode,
)
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.services import slack_socket_mode_bridge
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.use_cases.agent_api_keys_use_case import DAgentAPIKeysUseCase
from src.domain.use_cases.agents_use_case import DAgentsUseCase
from src.utils import credential_encryption
from src.utils.agent_api_key_authorization import (
    API_KEY_NOT_FOUND_MESSAGE,
    _check_api_key_or_collapse_to_404,
)
from src.utils.authorization_shortcuts import (
    DAuthorizedId,
    DAuthorizedResourceIds,
    _check_agent_or_collapse_to_404,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(
    prefix="/agent_api_keys",
    tags=["Agent APIKeys"],
)


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


@router.post(
    "",
    response_model=CreateAPIKeyResponse,
)
async def create_api_key(
    request: CreateAPIKeyRequest,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    agent_use_case: DAgentsUseCase,
    authorization_service: DAuthorizationService,
) -> CreateAPIKeyResponse:
    if not request.agent_id and not request.agent_name:
        raise HTTPException(
            status_code=400,
            detail="Either 'agent_id' or 'agent_name' must be provided to create an agent api_key.",
        )
    if request.agent_id and request.agent_name:
        raise HTTPException(
            status_code=400,
            detail="Only one of 'agent_id' or 'agent_name' should be provided to create an agent api_key.",
        )
    agent = await agent_use_case.get(id=request.agent_id, name=request.agent_name)

    # No api_key resource exists yet, so gate on the parent agent while keeping
    # hidden-vs-visible denied semantics consistent with other agent checks.
    await _check_agent_or_collapse_to_404(
        authorization_service,
        agent.id,
        AuthorizedOperationType.update,
    )

    # Check if external agent API key already exists for this name and agent ID
    existing_api_key = await agent_api_key_use_case.get_by_agent_id_and_name(
        agent_id=agent.id,
        name=request.name,
        api_key_type=request.api_key_type,
    )
    if existing_api_key:
        error_msg = f"{request.api_key_type} agent API key '{request.name}' already exists for agent ID {agent.id}."
        logger.error(error_msg)
        raise HTTPException(status_code=409, detail=error_msg)

    new_api_key = request.api_key or secrets.token_hex(32)
    agent_api_key_entity = await agent_api_key_use_case.create(
        agent_id=agent.id,
        api_key=str(new_api_key),
        name=request.name,
        api_key_type=request.api_key_type,
    )
    return CreateAPIKeyResponse(
        id=agent_api_key_entity.id,
        agent_id=agent_api_key_entity.agent_id,
        created_at=agent_api_key_entity.created_at,
        name=agent_api_key_entity.name,
        api_key_type=agent_api_key_entity.api_key_type,
        api_key=str(new_api_key),  # Return the inserted API key
    )


async def _check_app_token_belongs_to(app_token: str, app_id: str) -> None:
    try:
        token_app_id = await slack_socket_mode_bridge.read_slack_app_id(app_token)
    except slack_socket_mode_bridge.AppTokenRejected as exc:
        raise HTTPException(
            status_code=400, detail=f"Slack rejected app_token: {exc}."
        ) from exc
    except Exception as exc:
        logger.warning(
            "Reading the Slack app id for app_token failed (%s)", type(exc).__name__
        )
        raise HTTPException(
            status_code=502,
            detail="Could not confirm with Slack which app app_token belongs to; "
            "try again.",
        ) from exc
    if token_app_id != app_id:
        raise HTTPException(
            status_code=400,
            detail=f"app_token belongs to Slack app '{token_app_id}', not '{app_id}'.",
        )


def _slack_app_already_served(app_id: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=f"Slack app '{app_id}' is already served over Socket Mode by another "
        "trigger; delete that trigger first.",
    )


def _clean_forward_path(forward_path: str) -> str:
    cleaned = forward_path.lstrip("/")
    if _has_control_chars(cleaned):
        raise HTTPException(
            status_code=400,
            detail="forward_path must not contain control characters.",
        )
    return cleaned


async def _encrypt_checked_app_token(
    app_token: str,
    app_id: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    *,
    except_key_id: str | None = None,
) -> str:
    """Check an app token for the Slack app ``app_id`` and return it encrypted.

    ``except_key_id`` is the trigger being updated, which may already serve the app.
    """
    if not app_token.startswith("xapp-"):
        raise HTTPException(
            status_code=400,
            detail="app_token must be a Slack app-level token (xapp-...).",
        )
    if not credential_encryption.is_configured():
        raise HTTPException(
            status_code=503,
            detail="This deployment cannot store app tokens: credential "
            "encryption is not configured.",
        )
    # The app id is the trigger's name and is unique across agents, so an
    # unchecked one would let any caller reserve someone else's app.
    await _check_app_token_belongs_to(app_token, app_id)
    # Slack gives each event to one of an app's connections, so a second Socket
    # Mode trigger for the same app would take part of the first one's events. The
    # table's unique constraint enforces this; checking first keeps create()'s auth
    # registration from running for a request that is bound to fail.
    if await agent_api_key_use_case.has_slack_socket_mode_trigger(
        app_id, except_key_id=except_key_id
    ):
        raise _slack_app_already_served(app_id)
    return credential_encryption.encrypt(app_token)


@router.post(
    "/webhook-trigger",
    response_model=CreateWebhookTriggerResponse,
)
async def create_webhook_trigger(
    request: CreateWebhookTriggerRequest,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    agent_use_case: DAgentsUseCase,
    authorization_service: DAuthorizationService,
) -> CreateWebhookTriggerResponse:
    """Wire a webhook trigger in one call.

    Registers the source's signature-verification key (github/slack/linear) for the agent and
    returns the ready-to-paste forward webhook URL plus the signing secret (shown once).
    The webhook then flows through the existing /agents/forward ingress, which verifies
    the signature against this key. Bundles the existing key-create + URL composition so
    a UI (or a curl) can set up a trigger without two steps.
    """
    if request.source not in (
        AgentAPIKeyType.GITHUB,
        AgentAPIKeyType.SLACK,
        AgentAPIKeyType.LINEAR,
    ):
        raise HTTPException(
            status_code=400,
            detail="source must be 'github', 'slack' or 'linear' for a webhook trigger.",
        )
    agent = await agent_use_case.get(name=request.agent_name)

    # No api_key resource exists yet, so gate on the parent agent (update).
    await _check_agent_or_collapse_to_404(
        authorization_service,
        agent.id,
        AuthorizedOperationType.update,
    )

    existing_api_key = await agent_api_key_use_case.get_by_agent_id_and_name(
        agent_id=agent.id,
        name=request.name,
        api_key_type=request.source,
    )
    if existing_api_key:
        # A duplicate is an expected client condition (409), not a server error, and the
        # message avoids leaking the internal agent UUID the caller never supplied.
        raise HTTPException(
            status_code=409,
            detail=f"A {request.source} webhook key named '{request.name}' already exists for this agent.",
        )

    # GitHub lets you supply (and we can generate) a per-webhook secret to paste into the
    # repo's Secret field. Slack is different: it signs every request with the app's own
    # Signing Secret, so the caller must supply that exact value — a generated one would
    # never match, and validate_slack_delivery_webhook would reject every real delivery.
    # (See PR #329 discussion.)
    if request.source == AgentAPIKeyType.SLACK and not request.secret:
        raise HTTPException(
            status_code=400,
            detail=(
                "Slack triggers must supply 'secret' set to the Slack app's Signing Secret "
                "(from your app credentials); it can't be generated."
            ),
        )

    # Linear is the same: it signs every delivery with the OAuth app's webhook signing
    # secret, and the trigger's name must be the app's OAuth client id (the payload's
    # oauthClientId, which validate_linear_delivery_webhook looks the key up by).
    if request.source == AgentAPIKeyType.LINEAR and not request.secret:
        raise HTTPException(
            status_code=400,
            detail=(
                "Linear triggers must supply 'secret' set to the Linear OAuth app's webhook "
                "signing secret; it can't be generated."
            ),
        )

    forward_path = _clean_forward_path(request.forward_path)

    app_token_encrypted = None
    if request.app_token is not None:
        if request.source != AgentAPIKeyType.SLACK:
            raise HTTPException(
                status_code=400,
                detail="app_token is only supported for Slack triggers.",
            )
        app_token_encrypted = await _encrypt_checked_app_token(
            request.app_token, request.name, agent_api_key_use_case
        )

    secret = request.secret if request.secret is not None else secrets.token_hex(32)
    try:
        agent_api_key_entity = await agent_api_key_use_case.create(
            agent_id=agent.id,
            api_key=str(secret),
            name=request.name,
            api_key_type=request.source,
            slack_socket_mode_app_token_encrypted=app_token_encrypted,
            slack_socket_mode_forward_path=forward_path,
        )
    except DuplicateItemError:
        # Only the Socket Mode insert has a unique key a client can collide on: a
        # concurrent registration for the same app got there first.
        if app_token_encrypted is None:
            raise
        raise _slack_app_already_served(request.name) from None

    encoded_agent_name = quote(request.agent_name, safe="")
    encoded_forward_path = quote(forward_path, safe="/")
    webhook_path = f"/agents/forward/name/{encoded_agent_name}/{encoded_forward_path}"
    base_url = (request.base_url or os.environ.get("AGENTEX_PUBLIC_URL", "")).rstrip(
        "/"
    )
    webhook_url = f"{base_url}{webhook_path}" if base_url else None

    return CreateWebhookTriggerResponse(
        key_id=agent_api_key_entity.id,
        agent_name=request.agent_name,
        source=agent_api_key_entity.api_key_type,
        name=request.name,
        secret=str(secret),
        webhook_path=webhook_path,
        webhook_url=webhook_url,
    )


async def _slack_trigger_for_update(
    key_id: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    authorization_service: DAuthorizationService,
) -> AgentAPIKeyEntity:
    trigger = await agent_api_key_use_case.get(id=key_id)
    await _check_api_key_or_collapse_to_404(
        authorization_service, trigger.id, AuthorizedOperationType.read
    )
    # The same permission registering the trigger needed.
    await _check_agent_or_collapse_to_404(
        authorization_service, trigger.agent_id, AuthorizedOperationType.update
    )
    if not await agent_api_key_use_case.get_agent(agent_id=trigger.agent_id):
        raise ItemDoesNotExist(API_KEY_NOT_FOUND_MESSAGE)
    if trigger.api_key_type != AgentAPIKeyType.SLACK:
        raise HTTPException(
            status_code=400, detail="Socket Mode applies only to Slack triggers."
        )
    return trigger


@router.put(
    "/{id}/slack_socket_mode",
    response_model=SlackSocketMode,
    summary="Serve a Slack trigger over Socket Mode",
    description="Turn Socket Mode on for an existing Slack trigger, or replace its "
    "app token and forward path. The bridge picks the change up within a minute.",
)
async def set_slack_socket_mode(
    id: str,
    request: SetSlackSocketModeRequest,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    authorization_service: DAuthorizationService,
) -> SlackSocketMode:
    trigger = await _slack_trigger_for_update(
        id, agent_api_key_use_case, authorization_service
    )
    forward_path = _clean_forward_path(request.forward_path)
    app_token_encrypted = await _encrypt_checked_app_token(
        request.app_token,
        trigger.name,
        agent_api_key_use_case,
        except_key_id=trigger.id,
    )
    try:
        app = await agent_api_key_use_case.set_slack_socket_mode(
            trigger=trigger,
            app_token_encrypted=app_token_encrypted,
            forward_path=forward_path,
        )
    except DuplicateItemError:
        raise _slack_app_already_served(trigger.name) from None
    return SlackSocketMode(
        key_id=trigger.id, slack_app_id=app.slack_app_id, forward_path=app.forward_path
    )


@router.delete(
    "/{id}/slack_socket_mode",
    response_model=str,
    summary="Stop serving a Slack trigger over Socket Mode",
    description="Remove the trigger's app token. The trigger itself stays, and the "
    "bridge closes its connection within a minute.",
)
async def delete_slack_socket_mode(
    id: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    authorization_service: DAuthorizationService,
) -> str:
    trigger = await _slack_trigger_for_update(
        id, agent_api_key_use_case, authorization_service
    )
    if not await agent_api_key_use_case.delete_slack_socket_mode(trigger.id):
        raise HTTPException(
            status_code=404, detail="This trigger is not served over Socket Mode."
        )
    return f"Socket Mode turned off for agent API key {trigger.id}"


@router.get(
    "",
    response_model=list[AgentAPIKey],
    summary="List API keys for an agent ID",
    description="List API keys for an agent ID.",
)
async def list_agent_api_keys(
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    agent_use_case: DAgentsUseCase,
    authorized_api_key_ids: DAuthorizedResourceIds(
        AgentexResourceType.api_key, AuthorizedOperationType.read
    ),
    agent_id: str | None = None,
    agent_name: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    page_number: int = Query(default=1, ge=1),
) -> list[AgentAPIKey]:
    if not agent_id and not agent_name:
        raise HTTPException(
            status_code=400,
            detail="Either 'agent_id' or 'agent_name' must be provided to list agent api_keys.",
        )
    if agent_id and agent_name:
        raise HTTPException(
            status_code=400,
            detail="Only one of 'agent_id' or 'agent_name' should be provided to list agent api_keys.",
        )
    agent = await agent_use_case.get(id=agent_id, name=agent_name)
    # ``id`` filter runs at the SQL layer so limit/offset apply post-filter.
    # ``None`` = authz declined to enumerate (e.g. bypass); pass through.
    agent_api_key_entities = await agent_api_key_use_case.list(
        agent_id=agent.id,
        limit=limit,
        page_number=page_number,
        id=authorized_api_key_ids,
    )
    return [
        AgentAPIKey.model_validate(agent_api_key_entity)
        for agent_api_key_entity in agent_api_key_entities
    ]


@router.get(
    "/name/{name}",
    response_model=AgentAPIKey,
    summary="Return named API key for the agent ID",
    description="Return named API key for the agent ID.",
)
async def get_agent_api_key_by_name(
    name: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    agent_use_case: DAgentsUseCase,
    authorization_service: DAuthorizationService,
    agent_id: str | None = None,
    agent_name: str | None = None,
    api_key_type: AgentAPIKeyType = AgentAPIKeyType.EXTERNAL,
) -> AgentAPIKey:
    if not agent_id and not agent_name:
        raise HTTPException(
            status_code=400,
            detail="Either 'agent_id' or 'agent_name' must be provided to get an agent api_key.",
        )
    if agent_id and agent_name:
        raise HTTPException(
            status_code=400,
            detail="Only one of 'agent_id' or 'agent_name' should be provided to get an agent api_key.",
        )
    agent = await agent_use_case.get(id=agent_id, name=agent_name)
    agent_api_key_entity = await agent_api_key_use_case.get_by_agent_id_and_name(
        agent_id=agent.id, name=name, api_key_type=api_key_type
    )
    if not agent_api_key_entity:
        # Absent and denied 404s must be byte-for-byte identical — see
        # ``API_KEY_NOT_FOUND_MESSAGE``.
        raise ItemDoesNotExist(API_KEY_NOT_FOUND_MESSAGE)
    # Composite lookup key ``(agent_id, name, api_key_type)`` doesn't fit
    # ``DAuthorizedName`` — apply the collapse inline.
    await _check_api_key_or_collapse_to_404(
        authorization_service,
        agent_api_key_entity.id,
        AuthorizedOperationType.read,
    )
    return AgentAPIKey.model_validate(agent_api_key_entity)


@router.get(
    "/{id}",
    response_model=AgentAPIKey,
    summary="Return the API key by ID",
    description="Return API key by ID.",
)
async def get_agent_api_key(
    id: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    _authorized_id: DAuthorizedId(
        AgentexResourceType.api_key,
        AuthorizedOperationType.read,
        param_name="id",
    ),
) -> AgentAPIKey:
    agent_api_key_entity = await agent_api_key_use_case.get(id=id)
    return AgentAPIKey.model_validate(agent_api_key_entity)


@router.delete(
    "/{id}",
    response_model=str,
    summary="Delete API key by ID",
    description="Delete API key by ID.",
)
async def delete_agent_api_key(
    id: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    _authorized_id: DAuthorizedId(
        AgentexResourceType.api_key,
        AuthorizedOperationType.delete,
        param_name="id",
    ),
) -> str:
    # ``api_key.delete`` expands transitively to ``parent_agent->update``,
    # so the dep above enforces both factors.
    await agent_api_key_use_case.delete(id=id)
    return f"Agent API key with ID {id} deleted"


@router.delete(
    "/name/{api_key_name}",
    response_model=str,
    summary="Delete API key by name",
    description="Delete API key by name.",
)
async def delete_agent_api_key_by_name(
    api_key_name: str,
    agent_api_key_use_case: DAgentAPIKeysUseCase,
    agent_use_case: DAgentsUseCase,
    authorization_service: DAuthorizationService,
    agent_id: str | None = None,
    agent_name: str | None = None,
    api_key_type: AgentAPIKeyType = AgentAPIKeyType.EXTERNAL,
) -> str:
    if not agent_id and not agent_name:
        raise HTTPException(
            status_code=400,
            detail="Either 'agent_id' or 'agent_name' must be provided to delete an agent api_key.",
        )
    if agent_id and agent_name:
        raise HTTPException(
            status_code=400,
            detail="Only one of 'agent_id' or 'agent_name' should be provided to delete an agent api_key.",
        )
    agent = await agent_use_case.get(id=agent_id, name=agent_name)

    # Resolve name -> id, check, then delete by the resolved id. Deleting by
    # name would race: if the row were replaced between check and delete, the
    # check would evaluate the old id but the mutation would land on the new
    # one.
    existing = await agent_api_key_use_case.get_by_agent_id_and_name(
        agent_id=agent.id, name=api_key_name, api_key_type=api_key_type
    )
    if not existing:
        raise ItemDoesNotExist(API_KEY_NOT_FOUND_MESSAGE)
    await _check_api_key_or_collapse_to_404(
        authorization_service,
        existing.id,
        AuthorizedOperationType.delete,
    )
    await agent_api_key_use_case.delete(id=existing.id)

    return f"Agent api_key '{api_key_name}' deleted"
