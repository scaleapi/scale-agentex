from datetime import datetime

from pydantic import Field

from src.domain.entities.states import StateEntity
from src.domain.entities.task_messages import TaskMessageEntity
from src.utils.model_utils import BaseModel


class TaskSnapshotEntity(BaseModel):
    """
    Self-contained, restorable snapshot of a task's content surfaces.

    Used as the response body of GET /tasks/{id}/export and the request body of
    POST /tasks/{id}/rehydrate. Schema parity between the two directions is the
    invariant that makes export → clean → rehydrate a round-trip-equivalent
    operation.

    Scope note: tasks.params (JSONB) is intentionally NOT part of the snapshot
    or the cleanup surface for v1. It may carry initial-message content for
    some agents; if that becomes a compliance gap, add it as a follow-up.
    Events are also NOT included — they are a transient delivery surface;
    consumed events have no live readers (see agent_task_tracker cursor).
    """

    task_id: str
    messages: list[TaskMessageEntity] = Field(default_factory=list)
    task_states: list[StateEntity] = Field(default_factory=list)


class TaskCleanupResultEntity(BaseModel):
    """
    Per-invocation result of a cleanup operation.

    Returned to callers of POST /tasks/{id}/clean and emitted as a structured
    log line (forensic record). Not persisted to a dedicated table in v1 —
    Datadog log search is the audit trail.
    """

    task_id: str
    cleaned_at: datetime
    messages_deleted: int
    task_states_deleted: int
    events_deleted: int


class TaskExportToUrlResultEntity(BaseModel):
    """
    Per-invocation result of an export-to-URL operation. Returned to callers
    of POST /tasks/{id}/export so they can verify what was uploaded without
    having to re-download and parse.
    """

    task_id: str
    upload_url: str
    uploaded_bytes: int
    messages_count: int
    task_states_count: int
