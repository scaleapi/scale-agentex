from pydantic import BaseModel, Field, HttpUrl, model_validator

from src.domain.entities.states import StateEntity
from src.domain.entities.task_messages import TaskMessageEntity
from src.domain.entities.task_retention import (
    TaskCleanupResultEntity,
    TaskExportToUrlResultEntity,
    TaskSnapshotEntity,
)


class ExportTaskResponse(TaskSnapshotEntity):
    """Wire format mirrors the entity directly — schema parity is intentional."""

    pass


class ExportTaskToUrlRequest(BaseModel):
    upload_url: HttpUrl = Field(
        ...,
        description=(
            "Presigned PUT URL where Agentex will upload the task snapshot as "
            "JSON. Must be https; must resolve to a public address."
        ),
    )


class ExportTaskToUrlResponse(TaskExportToUrlResultEntity):
    pass


class CleanTaskRequest(BaseModel):
    force: bool = Field(
        default=False,
        description=(
            "Skip the idle-threshold check. Active-workflow and "
            "unprocessed-events checks still apply. Admin use only."
        ),
    )
    idle_days: int = Field(
        default=7,
        ge=1,
        description="Idle threshold in days (ignored when force=true).",
    )


class CleanTaskResponse(TaskCleanupResultEntity):
    pass


class RehydrateTaskRequest(BaseModel):
    """
    Either provide inline content (messages + task_states) or a snapshot_url
    pointing at a presigned JSON download. Mixing both is rejected.

    The inline form is the canonical shape used by export's GET response, so
    snapshot → clean → rehydrate round-trips cleanly without serialization
    changes.
    """

    task_id: str
    messages: list[TaskMessageEntity] = Field(default_factory=list)
    task_states: list[StateEntity] = Field(default_factory=list)
    snapshot_url: HttpUrl | None = Field(
        default=None,
        description=(
            "Presigned GET URL whose body is a JSON-encoded TaskSnapshotEntity. "
            "Must be https; must resolve to a public address. When set, "
            "messages/task_states must be empty."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_source(self):
        has_inline = bool(self.messages or self.task_states)
        has_url = self.snapshot_url is not None
        if has_inline and has_url:
            raise ValueError(
                "Provide inline content (messages/task_states) OR snapshot_url, "
                "not both."
            )
        return self
