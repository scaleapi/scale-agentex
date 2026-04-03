import base64

from fastapi import APIRouter, Response

from src.api.schemas.checkpoints import (
    BlobResponse,
    CheckpointListItem,
    CheckpointTupleResponse,
    DeleteThreadRequest,
    GetCheckpointTupleRequest,
    ListCheckpointsRequest,
    PutCheckpointRequest,
    PutCheckpointResponse,
    PutWritesRequest,
    WriteResponse,
)
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.use_cases.checkpoints_use_case import DCheckpointsUseCase
from src.utils.authorization_shortcuts import DAuthorizedBodyId
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/checkpoints", tags=["Checkpoints"])


def _bytes_to_b64(data: bytes | None) -> str | None:
    if data is None:
        return None
    return base64.b64encode(data).decode("ascii")


def _b64_to_bytes(data: str | None) -> bytes | None:
    if data is None:
        return None
    return base64.b64decode(data)


@router.post(
    "/get-tuple",
    response_model=CheckpointTupleResponse | None,
)
async def get_checkpoint_tuple(
    request: GetCheckpointTupleRequest,
    checkpoints_use_case: DCheckpointsUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.read, field_name="thread_id"
    ),
) -> CheckpointTupleResponse | None:
    result = await checkpoints_use_case.get_tuple(
        thread_id=request.thread_id,
        checkpoint_ns=request.checkpoint_ns,
        checkpoint_id=request.checkpoint_id,
    )
    if result is None:
        return None

    return CheckpointTupleResponse(
        thread_id=result["thread_id"],
        checkpoint_ns=result["checkpoint_ns"],
        checkpoint_id=result["checkpoint_id"],
        parent_checkpoint_id=result["parent_checkpoint_id"],
        checkpoint=result["checkpoint"],
        metadata=result["metadata"],
        blobs=[
            BlobResponse(
                channel=b["channel"],
                version=b["version"],
                type=b["type"],
                blob=_bytes_to_b64(b["blob"]),
            )
            for b in result.get("blobs", [])
        ],
        pending_writes=[
            WriteResponse(
                task_id=w["task_id"],
                idx=w["idx"],
                channel=w["channel"],
                type=w["type"],
                blob=_bytes_to_b64(w["blob"]),
            )
            for w in result.get("pending_writes", [])
        ],
    )


@router.post(
    "/put",
    response_model=PutCheckpointResponse,
)
async def put_checkpoint(
    request: PutCheckpointRequest,
    checkpoints_use_case: DCheckpointsUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.execute, field_name="thread_id"
    ),
) -> PutCheckpointResponse:
    blobs = [
        {
            "channel": b.channel,
            "version": b.version,
            "type": b.type,
            "blob": _b64_to_bytes(b.blob),
        }
        for b in request.blobs
    ]

    await checkpoints_use_case.put(
        thread_id=request.thread_id,
        checkpoint_ns=request.checkpoint_ns,
        checkpoint_id=request.checkpoint_id,
        parent_checkpoint_id=request.parent_checkpoint_id,
        checkpoint=request.checkpoint,
        metadata=request.metadata,
        blobs=blobs,
    )

    return PutCheckpointResponse(
        thread_id=request.thread_id,
        checkpoint_ns=request.checkpoint_ns,
        checkpoint_id=request.checkpoint_id,
    )


@router.post(
    "/put-writes",
    status_code=204,
)
async def put_writes(
    request: PutWritesRequest,
    checkpoints_use_case: DCheckpointsUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.execute, field_name="thread_id"
    ),
) -> Response:
    writes = [
        {
            "task_id": w.task_id,
            "idx": w.idx,
            "channel": w.channel,
            "type": w.type,
            "blob": _b64_to_bytes(w.blob),
            "task_path": w.task_path,
        }
        for w in request.writes
    ]

    await checkpoints_use_case.put_writes(
        thread_id=request.thread_id,
        checkpoint_ns=request.checkpoint_ns,
        checkpoint_id=request.checkpoint_id,
        writes=writes,
        upsert=request.upsert,
    )

    return Response(status_code=204)


@router.post(
    "/list",
    response_model=list[CheckpointListItem],
)
async def list_checkpoints(
    request: ListCheckpointsRequest,
    checkpoints_use_case: DCheckpointsUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.read, field_name="thread_id"
    ),
) -> list[CheckpointListItem]:
    results = await checkpoints_use_case.list_checkpoints(
        thread_id=request.thread_id,
        checkpoint_ns=request.checkpoint_ns,
        before_checkpoint_id=request.before_checkpoint_id,
        filter_metadata=request.filter_metadata,
        limit=request.limit,
    )

    return [
        CheckpointListItem(
            thread_id=r["thread_id"],
            checkpoint_ns=r["checkpoint_ns"],
            checkpoint_id=r["checkpoint_id"],
            parent_checkpoint_id=r["parent_checkpoint_id"],
            checkpoint=r["checkpoint"],
            metadata=r["metadata"],
        )
        for r in results
    ]


@router.post(
    "/delete-thread",
    status_code=204,
)
async def delete_thread(
    request: DeleteThreadRequest,
    checkpoints_use_case: DCheckpointsUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.delete, field_name="thread_id"
    ),
) -> Response:
    await checkpoints_use_case.delete_thread(thread_id=request.thread_id)
    return Response(status_code=204)
