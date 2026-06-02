import secrets

from fastapi import APIRouter, HTTPException, Query

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.agent_api_keys import (
    AgentAPIKey,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
)
from src.api.schemas.authorization_types import (
    AgentexResource,
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

    # Parent-agent FGAC: only callers with ``update`` on the parent agent may
    # mint a new api_key under it. The new api_key has no resource row yet, so
    # this is the only enforcement surface at create time. SpiceDB cannot
    # transitively gate on a not-yet-created child.
    await authorization_service.check(
        resource=AgentexResource.agent(agent.id),
        operation=AuthorizedOperationType.update,
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
    # Push the FGAC id-filter into the repo so pagination + limit apply
    # post-filter at the SQL layer. ``None`` means the authz backend declined
    # to enumerate (e.g. bypass) — pass through unfiltered.
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
        # Identifier-free message must match the denied-resource branch of
        # ``_check_api_key_or_collapse_to_404`` so absent-vs-denied 404s are
        # byte-for-byte indistinguishable (cross-tenant existence leak).
        raise ItemDoesNotExist(API_KEY_NOT_FOUND_MESSAGE)
    # Name routes for api_key don't fit ``DAuthorizedName`` (the lookup key is
    # ``(agent_id, name, api_key_type)``, not a single globally-unique name
    # path param). Apply the collapse helper explicitly so present-but-denied
    # surfaces as 404, mirroring tasks' name route in PR #249.
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
    # Two-factor mutation: SpiceDB's ``api_key.delete`` permission depends
    # transitively on ``parent_agent->update`` per the schema, so the
    # ``DAuthorizedId(..., delete)`` dep above enforces both api_key.delete
    # and the parent-agent.update factor. No explicit second
    # ``authorization_service.check`` on the parent agent is needed (matches
    # Asher's PR #249 approach for tasks).
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

    # Resolve name -> id, then run the collapse-wrapped delete check before
    # mutating. Two-factor (api_key.delete & parent_agent->update) is
    # transitively enforced by the SpiceDB schema definition of
    # ``api_key.delete``; we don't repeat a parent check here.
    existing = await agent_api_key_use_case.get_by_agent_id_and_name(
        agent_id=agent.id, name=api_key_name, api_key_type=api_key_type
    )
    if not existing:
        # Same identifier-free 404 as the denied branch — see the analogous
        # comment in ``get_agent_api_key_by_name`` above.
        raise ItemDoesNotExist(API_KEY_NOT_FOUND_MESSAGE)
    await _check_api_key_or_collapse_to_404(
        authorization_service,
        existing.id,
        AuthorizedOperationType.delete,
    )

    await agent_api_key_use_case.delete_by_agent_id_and_key_name(
        agent_id=agent.id,
        key_name=api_key_name,
        api_key_type=api_key_type,
    )

    return f"Agent api_key '{api_key_name}' deleted"
