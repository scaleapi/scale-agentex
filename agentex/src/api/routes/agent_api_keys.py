import os
import secrets

from fastapi import APIRouter, HTTPException, Query

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.agent_api_keys import (
    AgentAPIKey,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    CreateWebhookTriggerRequest,
    CreateWebhookTriggerResponse,
)
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.use_cases.agent_api_keys_use_case import DAgentAPIKeysUseCase
from src.domain.use_cases.agents_use_case import DAgentsUseCase
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

    Registers the source's signature-verification key (github/slack) for the agent and
    returns the ready-to-paste forward webhook URL plus the signing secret (shown once).
    The webhook then flows through the existing /agents/forward ingress, which verifies
    the signature against this key. Bundles the existing key-create + URL composition so
    a UI (or a curl) can set up a trigger without two steps.
    """
    if request.source not in (AgentAPIKeyType.GITHUB, AgentAPIKeyType.SLACK):
        raise HTTPException(
            status_code=400,
            detail="source must be 'github' or 'slack' for a webhook trigger.",
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

    secret = request.secret or secrets.token_hex(32)
    agent_api_key_entity = await agent_api_key_use_case.create(
        agent_id=agent.id,
        api_key=str(secret),
        name=request.name,
        api_key_type=request.source,
    )

    forward_path = request.forward_path.lstrip("/")
    webhook_path = f"/agents/forward/name/{request.agent_name}/{forward_path}"
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
