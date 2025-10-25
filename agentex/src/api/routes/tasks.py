from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.delete_response import DeleteResponse
from src.api.schemas.tasks import Task, UpdateTaskRequest
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.use_cases.streams_use_case import DStreamsUseCase
from src.domain.use_cases.tasks_use_case import DTaskUseCase
from src.utils.authorization_shortcuts import (
    DAuthorizedId,
    DAuthorizedName,
    DAuthorizedResourceIds,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


@router.get(
    "/{task_id}",
    response_model=Task,
    summary="Get Task by ID",
    description="Get a task by its unique ID.",
)
async def get_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.read),
    task_use_case: DTaskUseCase,
) -> Task:
    task_entity = await task_use_case.get_task(id=task_id)
    return Task.model_validate(task_entity)


@router.get(
    "/name/{task_name}",
    response_model=Task,
    summary="Get Task by Name",
    description="Get a task by its unique name.",
)
async def get_task_by_name(
    task_name: DAuthorizedName(AgentexResourceType.task, AuthorizedOperationType.read),
    task_use_case: DTaskUseCase,
) -> Task:
    """Get a task by its unique name."""
    task_entity = await task_use_case.get_task(name=task_name)
    return Task.model_validate(task_entity)


@router.get(
    "",
    response_model=list[Task],
    summary="List Tasks",
    description="List all tasks.",
)
async def list_tasks(
    task_use_case: DTaskUseCase,
    authorized_ids: DAuthorizedResourceIds(AgentexResourceType.task),
    agent_id: str | None = None,
    agent_name: str | None = None,
    limit: int = 50,
    page_number: int = 1,
):
    """List all tasks."""

    task_entities = await task_use_case.list_tasks(
        id=authorized_ids,
        agent_id=agent_id,
        agent_name=agent_name,
        limit=limit,
        page_number=page_number,
    )
    return [Task.model_validate(task_entity) for task_entity in task_entities]


@router.delete(
    "/{task_id}",
    summary="Delete Task by ID",
    description="Delete a task by its unique ID.",
)
async def delete_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.delete),
    task_use_case: DTaskUseCase,
    authorization: DAuthorizationService,
) -> DeleteResponse:
    await task_use_case.delete_task(id=task_id)
    await authorization.revoke(AgentexResource.task(task_id))
    return DeleteResponse(id=task_id, message=f"Task {task_id} deleted successfully")


@router.delete(
    "/name/{task_name}",
    summary="Delete Task by Name",
    description="Delete a task by its unique name.",
)
async def delete_task_by_name(
    task_name: DAuthorizedName(
        AgentexResourceType.task, AuthorizedOperationType.delete
    ),
    task_use_case: DTaskUseCase,
    authorization: DAuthorizationService,
) -> DeleteResponse:
    task_entity = await task_use_case.get_task(name=task_name)
    await task_use_case.delete_task(name=task_name)
    await authorization.revoke(AgentexResource.task(task_entity.id))
    return DeleteResponse(
        id=task_entity.id, message=f"Task '{task_name}' deleted successfully"
    )


@router.put(
    "/{task_id}",
    response_model=Task,
    summary="Update Task by ID",
    description="Update mutable fields for a task by its unique ID.",
)
async def update_task(
    request: UpdateTaskRequest,
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    task_use_case: DTaskUseCase,
) -> Task:
    updated_task_entity = await task_use_case.update_mutable_fields_on_task(
        id=task_id, task_metadata=request.task_metadata
    )
    return Task.model_validate(updated_task_entity)


@router.put(
    "/name/{task_name}",
    response_model=Task,
    summary="Update Task by Name",
    description="Update mutable fields for a task by its unique Name.",
)
async def update_task_by_name(
    request: UpdateTaskRequest,
    task_name: DAuthorizedName(
        AgentexResourceType.task, AuthorizedOperationType.update
    ),
    task_use_case: DTaskUseCase,
) -> Task:
    updated_task_entity = await task_use_case.update_mutable_fields_on_task(
        name=task_name, task_metadata=request.task_metadata
    )
    return Task.model_validate(updated_task_entity)


@router.get(
    "/{task_id}/stream",
    summary="Stream Task Events by ID",
    description="Stream events for a task by its unique ID.",
)
async def stream_task_events(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.read),
    stream_use_case: DStreamsUseCase,
) -> StreamingResponse:
    """
    Streams task events using Server-Sent Events (SSE).
    """

    return StreamingResponse(
        stream_use_case.stream_task_events(task_id=task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/name/{task_name}/stream",
    summary="Stream Task Events by Name",
    description="Stream events for a task by its unique name.",
)
async def stream_task_events_by_name(
    task_name: DAuthorizedName(AgentexResourceType.task, AuthorizedOperationType.read),
    stream_use_case: DStreamsUseCase,
) -> StreamingResponse:
    """
    Streams task events using Server-Sent Events (SSE) by task name.
    """

    return StreamingResponse(
        stream_use_case.stream_task_events(task_name=task_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
