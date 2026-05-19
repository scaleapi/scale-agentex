from pydantic import BaseModel, Field

from src.domain.entities.task_retention import (
    TaskCleanupResultEntity,
    TaskSnapshotEntity,
)


class ExportTaskResponse(TaskSnapshotEntity):
    """Wire format mirrors the entity directly — schema parity is intentional."""

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


class RehydrateTaskRequest(TaskSnapshotEntity):
    """Same shape as the export response — round-trip parity."""

    pass
