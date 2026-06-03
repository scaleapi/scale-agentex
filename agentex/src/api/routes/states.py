from fastapi import APIRouter, Query

from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
    TaskChildResourceType,
)
from src.api.schemas.states import CreateStateRequest, State, UpdateStateRequest
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.use_cases.states_use_case import DStatesUseCase
from src.utils.authorization_shortcuts import (
    DAuthorizedBodyId,
    DAuthorizedId,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)


router = APIRouter(prefix="/states", tags=["States"])

# AGX1-237 defines manage_access as a creator/owner-only task permission.
_STATE_WRITE_OPERATION = AuthorizedOperationType.manage_access


@router.post(
    "",
    response_model=State,
)
async def create_task_state(
    request: CreateStateRequest,
    states_use_case: DStatesUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, _STATE_WRITE_OPERATION
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
    # Will raise an exception if the state does not exist
    state_entity = await states_use_case.get(id=state_id)
    return State.model_validate(state_entity)


@router.get(
    "",
    response_model=list[State],
    summary="List States",
    description="List all states, optionally filtered by query parameters.",
)
async def filter_states(
    states_use_case: DStatesUseCase,
    authorization: DAuthorizationService,
    task_id: str | None = Query(None, description="Task ID"),
    agent_id: str | None = Query(None, description="Agent ID"),
    limit: int = Query(50, description="Limit", ge=1),
    page_number: int = Query(1, description="Page number", ge=1),
    order_by: str | None = Query(None, description="Field to order by"),
    order_direction: str = Query("desc", description="Order direction (asc or desc)"),
) -> list[State]:
    authorized_task_ids: list[str] | None = None
    if task_id is not None:
        try:
            await authorization.check(
                resource=AgentexResource.task(task_id),
                operation=AuthorizedOperationType.read,
            )
        except AuthorizationError:
            raise ItemDoesNotExist(f"Item with id '{task_id}' does not exist.") from None
    else:
        maybe_ids_iterable = await authorization.list_resources(
            filter_resource=AgentexResourceType.task,
            filter_operation=AuthorizedOperationType.read,
        )
        authorized_task_ids = (
            list(maybe_ids_iterable) if maybe_ids_iterable is not None else None
        )

    state_entities = await states_use_case.list(
        task_id=task_id,
        agent_id=agent_id,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
        authorized_task_ids=authorized_task_ids,
    )
    logger.info(f"Listing states: {state_entities}")
    return [State.model_validate(state_entity) for state_entity in state_entities]


@router.put(
    "/{state_id}",
    response_model=State,
)
async def update_task_state(
    request: UpdateStateRequest,
    state_id: DAuthorizedId(TaskChildResourceType.state, _STATE_WRITE_OPERATION),
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
    # Will raise an exception if the state does not exist
    state_entity = await states_use_case.get(id=state_id)
    await states_use_case.delete(id=state_id)
    return State.model_validate(state_entity)
