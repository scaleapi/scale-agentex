import json
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.adapters.temporal.adapter_temporal import DTemporalAdapter
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.delete_response import DeleteResponse
from src.api.schemas.tasks import (
    Task,
    TaskRelationships,
    TaskResponse,
    TaskStatus,
    TaskStatusReasonRequest,
    UpdateTaskRequest,
)
from src.domain.entities.tasks import TaskStatus as DomainTaskStatus
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
    response_model=TaskResponse,
    summary="Get Task by ID",
    description="Get a task by its unique ID.",
)
async def get_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.read),
    task_use_case: DTaskUseCase,
    relationships: Annotated[list[TaskRelationships], Query()] = None,
) -> TaskResponse:
    task_entity = await task_use_case.get_task(id=task_id, relationships=relationships)
    return TaskResponse.model_validate(task_entity)


@router.get(
    "/name/{task_name}",
    response_model=TaskResponse,
    summary="Get Task by Name",
    description="Get a task by its unique name.",
)
async def get_task_by_name(
    task_name: DAuthorizedName(AgentexResourceType.task, AuthorizedOperationType.read),
    task_use_case: DTaskUseCase,
    relationships: Annotated[list[TaskRelationships], Query()] = None,
) -> TaskResponse:
    """Get a task by its unique name."""
    task_entity = await task_use_case.get_task(
        name=task_name, relationships=relationships
    )
    return TaskResponse.model_validate(task_entity)


@router.get(
    "",
    response_model=list[TaskResponse],
    summary="List Tasks",
    description="List all tasks.",
)
async def list_tasks(
    task_use_case: DTaskUseCase,
    authorized_ids: DAuthorizedResourceIds(AgentexResourceType.task),
    agent_id: str | None = None,
    agent_name: str | None = None,
    status: Annotated[
        TaskStatus | None,
        Query(description="Filter tasks by status (e.g. RUNNING, COMPLETED)."),
    ] = None,
    task_metadata: Annotated[
        str | None,
        Query(
            description=(
                "JSON-encoded object used to filter tasks via JSONB containment. "
                'Example: {"created_by_user_id": "abc-123"}.'
            )
        ),
    ] = None,
    limit: int = 50,
    page_number: int = 1,
    order_by: str | None = None,
    order_direction: str = "desc",
    relationships: Annotated[list[TaskRelationships], Query()] = None,
):
    """List all tasks."""
    parsed_metadata: dict | None = None
    if task_metadata is not None:
        try:
            parsed_metadata = json.loads(task_metadata)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON in task_metadata query parameter: {exc.msg}",
            ) from exc
        if not isinstance(parsed_metadata, dict):
            raise HTTPException(
                status_code=400,
                detail="task_metadata must decode to a JSON object.",
            )
        if not parsed_metadata:
            raise HTTPException(
                status_code=400,
                detail="task_metadata cannot be empty; omit the parameter to skip filtering.",
            )

    if status == TaskStatus.DELETED:
        # list_tasks always excludes DELETED rows at the repository layer, so
        # filtering on it would silently return an empty list. Reject explicitly.
        raise HTTPException(
            status_code=400,
            detail="Cannot filter by DELETED status; deleted tasks are not returned by list_tasks.",
        )
    domain_status = DomainTaskStatus(status.value) if status is not None else None

    task_entities = await task_use_case.list_tasks(
        id=authorized_ids,
        agent_id=agent_id,
        agent_name=agent_name,
        status=domain_status,
        task_metadata=parsed_metadata,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
        relationships=relationships,
    )
    return [TaskResponse.model_validate(task_entity) for task_entity in task_entities]


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


@router.post(
    "/{task_id}/complete",
    response_model=Task,
    summary="Complete Task",
    description="Mark a running task as completed.",
)
async def complete_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    task_use_case: DTaskUseCase,
    request: TaskStatusReasonRequest | None = None,
) -> Task:
    updated = await task_use_case.complete_task(
        id=task_id, reason=request.reason if request else None
    )
    return Task.model_validate(updated)


@router.post(
    "/{task_id}/fail",
    response_model=Task,
    summary="Fail Task",
    description="Mark a running task as failed.",
)
async def fail_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    task_use_case: DTaskUseCase,
    request: TaskStatusReasonRequest | None = None,
) -> Task:
    updated = await task_use_case.fail_task(
        id=task_id, reason=request.reason if request else None
    )
    return Task.model_validate(updated)


@router.post(
    "/{task_id}/cancel",
    response_model=Task,
    summary="Cancel Task",
    description="Mark a running task as canceled.",
)
async def cancel_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    task_use_case: DTaskUseCase,
    request: TaskStatusReasonRequest | None = None,
) -> Task:
    updated = await task_use_case.cancel_task(
        id=task_id, reason=request.reason if request else None
    )
    return Task.model_validate(updated)


@router.post(
    "/{task_id}/terminate",
    response_model=Task,
    summary="Terminate Task",
    description="Mark a running task as terminated.",
)
async def terminate_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    task_use_case: DTaskUseCase,
    request: TaskStatusReasonRequest | None = None,
) -> Task:
    updated = await task_use_case.terminate_task(
        id=task_id, reason=request.reason if request else None
    )
    return Task.model_validate(updated)


@router.post(
    "/{task_id}/timeout",
    response_model=Task,
    summary="Timeout Task",
    description="Mark a running task as timed out.",
)
async def timeout_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    task_use_case: DTaskUseCase,
    request: TaskStatusReasonRequest | None = None,
) -> Task:
    updated = await task_use_case.timeout_task(
        id=task_id, reason=request.reason if request else None
    )
    return Task.model_validate(updated)


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


@router.get(
    "/{task_id}/query/{query_name}",
    summary="Query Task Workflow",
    description="Query a Temporal workflow associated with a task for its current state.",
)
async def query_task_workflow(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.read),
    query_name: str,
    temporal_adapter: DTemporalAdapter,
) -> dict[str, Any]:
    """
    Query a Temporal workflow by task ID and query name.
    Returns the query result from the workflow.
    """
    result = await temporal_adapter.query_workflow(
        workflow_id=task_id,
        query=query_name,
    )
    return {"task_id": task_id, "query": query_name, "result": result}
