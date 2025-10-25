from fastapi import APIRouter, HTTPException, Query

from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
    TaskChildResourceType,
)
from src.api.schemas.states import CreateStateRequest, State, UpdateStateRequest
from src.domain.use_cases.states_use_case import DStatesUseCase
from src.utils.authorization_shortcuts import DAuthorizedBodyId, DAuthorizedId
from src.utils.logging import make_logger

logger = make_logger(__name__)


router = APIRouter(prefix="/states", tags=["States"])


@router.post(
    "",
    response_model=State,
)
async def create_task_state(
    request: CreateStateRequest,
    states_use_case: DStatesUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.update
    ),
) -> State:
    state_entity = await states_use_case.create(
        task_id=request.task_id,
        agent_id=request.agent_id,
        state=request.state,
    )
    return State.model_validate(state_entity)


@router.get(
    "/{state_id}",
    response_model=State,
    summary="Get State by State ID",
    description="Get a state by its unique state ID.",
)
async def get_state(
    state_id: DAuthorizedId(TaskChildResourceType.state, AuthorizedOperationType.read),
    states_use_case: DStatesUseCase,
) -> State:
    state_entity = await states_use_case.get(id=state_id)
    if not state_entity:
        raise HTTPException(404, "State not found")
    return State.model_validate(state_entity)


@router.get(
    "",
    response_model=list[State],
    summary="List States",
    description="List all states, optionally filtered by query parameters.",
)
async def filter_states(
    states_use_case: DStatesUseCase,
    task_id: str | None = Query(None, description="Task ID"),
    agent_id: str | None = Query(None, description="Agent ID"),
) -> list[State]:
    state_entities = await states_use_case.list(task_id=task_id, agent_id=agent_id)
    logger.info(f"Listing states: {state_entities}")
    return [State.model_validate(state_entity) for state_entity in state_entities]


@router.put(
    "/{state_id}",
    response_model=State,
)
async def update_task_state(
    request: UpdateStateRequest,
    state_id: DAuthorizedId(
        TaskChildResourceType.state, AuthorizedOperationType.update
    ),
    states_use_case: DStatesUseCase,
) -> State:
    state_entity = await states_use_case.update(
        id=state_id,
        task_id=request.task_id,
        state=request.state,
    )
    return State.model_validate(state_entity)


@router.delete(
    "/{state_id}",
    response_model=State,
)
async def delete_task_state(
    state_id: DAuthorizedId(
        TaskChildResourceType.state, AuthorizedOperationType.delete
    ),
    states_use_case: DStatesUseCase,
) -> State:
    state_entity = await states_use_case.get(id=state_id)
    if not state_entity:
        raise HTTPException(404, "State not found")
    await states_use_case.delete(id=state_id)
    return State.model_validate(state_entity)
