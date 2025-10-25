import secrets

from fastapi import APIRouter, HTTPException

from src.api.schemas.agent_api_keys import (
    AgentAPIKey,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
)
from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.use_cases.agent_api_keys_use_case import DAgentAPIKeysUseCase
from src.domain.use_cases.agents_use_case import DAgentsUseCase
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
    agent_id: str | None = None,
    agent_name: str | None = None,
    limit: int = 50,
    page_number: int = 1,
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
    agent_api_key_entities = await agent_api_key_use_case.list(
        agent_id=agent.id, limit=limit, page_number=page_number
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
        raise HTTPException(
            status_code=404,
            detail=f"Agent api_key '{name}' not found for agent ID {agent.id}",
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
) -> str:
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
    await agent_api_key_use_case.delete_by_agent_id_and_key_name(
        agent_id=agent.id, key_name=api_key_name, api_key_type=api_key_type
    )

    return f"Agent api_key '{api_key_name}' deleted"
