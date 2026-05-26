"""
Task retention endpoints — export / clean / rehydrate.

These power both local-dev testing of the round-trip and the long-term
admin / external-caller integration surface. The scheduled Temporal cleanup
workflow calls the same use case (TaskRetentionUseCase.clean_task), not
these endpoints.

Authorization mirrors the existing /tasks routes via DAuthorizedId:
- export → read (returns content)
- rehydrate → update (writes content for a task the caller owns)
- clean → delete (destructive)
"""

from fastapi import APIRouter

from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.task_retention import (
    CleanTaskRequest,
    CleanTaskResponse,
    ExportTaskResponse,
    ExportTaskToUrlRequest,
    ExportTaskToUrlResponse,
    RehydrateTaskRequest,
)
from src.domain.entities.task_retention import TaskSnapshotEntity
from src.domain.use_cases.task_retention_use_case import DTaskRetentionUseCase
from src.utils.authorization_shortcuts import DAuthorizedId

router = APIRouter(prefix="/tasks", tags=["task-retention"])


@router.get(
    "/{task_id}/export",
    response_model=ExportTaskResponse,
)
async def export_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.read),
    use_case: DTaskRetentionUseCase,
) -> ExportTaskResponse:
    """
    Build a self-contained snapshot of a task's content surfaces.

    Returns the exact payload format that POST /rehydrate accepts, so
    export → clean → rehydrate is a round-trip-equivalent operation.
    """
    snapshot = await use_case.export_task(task_id)
    return ExportTaskResponse.model_validate(snapshot)


@router.post(
    "/{task_id}/export",
    response_model=ExportTaskToUrlResponse,
)
async def export_task_to_url(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.read),
    request: ExportTaskToUrlRequest,
    use_case: DTaskRetentionUseCase,
) -> ExportTaskToUrlResponse:
    """
    Build the task snapshot and PUT it to a caller-supplied presigned URL.

    Use this when the snapshot is too large for a JSON response body (long
    conversations, deep reasoning content, many attachments). The upload URL
    must be https and resolve to a public address — see SSRF guard.
    """
    result = await use_case.export_task_to_url(
        task_id=task_id,
        upload_url=str(request.upload_url),
    )
    return ExportTaskToUrlResponse.model_validate(result)


@router.post(
    "/{task_id}/clean",
    response_model=CleanTaskResponse,
)
async def clean_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.delete),
    request: CleanTaskRequest,
    use_case: DTaskRetentionUseCase,
) -> CleanTaskResponse:
    """
    Delete content-bearing rows for a stale task.

    Refuses on active tasks, in-flight workflows, or unprocessed events
    regardless of `force`. The `force=true` flag only bypasses the
    idle-threshold check.
    """
    audit = await use_case.clean_task(
        task_id=task_id,
        force=request.force,
        idle_days=request.idle_days,
    )
    return CleanTaskResponse.model_validate(audit)


@router.post(
    "/{task_id}/rehydrate",
    status_code=204,
)
async def rehydrate_task(
    task_id: DAuthorizedId(AgentexResourceType.task, AuthorizedOperationType.update),
    request: RehydrateTaskRequest,
    use_case: DTaskRetentionUseCase,
) -> None:
    """
    Restore content-bearing rows from a snapshot.

    Two modes:
    - Inline: caller provides messages and task_states in the request body.
    - URL: caller provides snapshot_url; Agentex downloads and parses it.

    Refuses if the task isn't currently in a cleaned state, or if any supplied
    message/state ID already exists in Mongo (catches double-rehydrate).
    """
    if request.snapshot_url is not None:
        await use_case.rehydrate_task(
            task_id=task_id,
            snapshot_url=str(request.snapshot_url),
        )
    else:
        snapshot = TaskSnapshotEntity(
            task_id=request.task_id,
            messages=request.messages,
            task_states=request.task_states,
        )
        await use_case.rehydrate_task(task_id=task_id, snapshot=snapshot)
