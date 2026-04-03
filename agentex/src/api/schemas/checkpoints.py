from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Request models ──


class GetCheckpointTupleRequest(BaseModel):
    thread_id: str = Field(..., title="Thread ID")
    checkpoint_ns: str = Field("", title="Checkpoint namespace")
    checkpoint_id: str | None = Field(None, title="Checkpoint ID (None = latest)")


class PutCheckpointRequest(BaseModel):
    thread_id: str = Field(..., title="Thread ID")
    checkpoint_ns: str = Field("", title="Checkpoint namespace")
    checkpoint_id: str = Field(..., title="Checkpoint ID")
    parent_checkpoint_id: str | None = Field(None, title="Parent checkpoint ID")
    checkpoint: dict[str, Any] = Field(..., title="Checkpoint JSONB payload")
    metadata: dict[str, Any] = Field(default_factory=dict, title="Checkpoint metadata")
    blobs: list[BlobData] = Field(default_factory=list, title="Channel blob data")


class BlobData(BaseModel):
    channel: str = Field(..., title="Channel name")
    version: str = Field(..., title="Channel version")
    type: str = Field(..., title="Serialization type tag")
    blob: str | None = Field(None, title="Base64-encoded binary data")


# Rebuild PutCheckpointRequest now that BlobData is defined
PutCheckpointRequest.model_rebuild()


class WriteData(BaseModel):
    task_id: str = Field(..., title="Task ID")
    idx: int = Field(..., title="Write index")
    channel: str = Field(..., title="Channel name")
    type: str | None = Field(None, title="Serialization type tag")
    blob: str = Field(..., title="Base64-encoded binary data")
    task_path: str = Field("", title="Task path")


class PutWritesRequest(BaseModel):
    thread_id: str = Field(..., title="Thread ID")
    checkpoint_ns: str = Field("", title="Checkpoint namespace")
    checkpoint_id: str = Field(..., title="Checkpoint ID")
    writes: list[WriteData] = Field(..., title="Write data")
    upsert: bool = Field(False, title="Upsert mode")


class ListCheckpointsRequest(BaseModel):
    thread_id: str = Field(..., title="Thread ID")
    checkpoint_ns: str | None = Field(None, title="Checkpoint namespace")
    before_checkpoint_id: str | None = Field(None, title="Before checkpoint ID")
    filter_metadata: dict[str, Any] | None = Field(
        None, title="Metadata filter (JSONB @>)"
    )
    limit: int = Field(100, title="Max results", ge=1, le=1000)


class DeleteThreadRequest(BaseModel):
    thread_id: str = Field(..., title="Thread ID")


# ── Response models ──


class BlobResponse(BaseModel):
    channel: str
    version: str
    type: str
    blob: str | None = None  # base64


class WriteResponse(BaseModel):
    task_id: str
    idx: int
    channel: str
    type: str | None = None
    blob: str | None = None  # base64


class CheckpointTupleResponse(BaseModel):
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    checkpoint: dict[str, Any]
    metadata: dict[str, Any]
    blobs: list[BlobResponse] = Field(default_factory=list)
    pending_writes: list[WriteResponse] = Field(default_factory=list)


class CheckpointListItem(BaseModel):
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    checkpoint: dict[str, Any]
    metadata: dict[str, Any]


class PutCheckpointResponse(BaseModel):
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
