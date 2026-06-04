from typing import Annotated

from fastapi import Depends

from src.domain.entities.task_retention import (
    TaskCleanupResultEntity,
    TaskExportToUrlResultEntity,
    TaskSnapshotEntity,
)
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.task_retention_service import DTaskRetentionService


class TaskRetentionUseCase:
    """
    Orchestrates export / clean / rehydrate operations for retention compliance.
    Backs both the HTTP admin endpoints and the Temporal scheduled cleanup
    activity; keep this layer thin so both callers exercise identical logic.
    """

    def __init__(self, retention_service: DTaskRetentionService):
        self.retention_service = retention_service

    @property
    def task_repository(self) -> TaskRepository:
        """Stable accessor for the underlying task repository so callers (e.g. the
        Temporal worker) can reuse the same instance without reaching through the
        service's internals."""
        return self.retention_service.task_repository

    async def export_task(self, task_id: str) -> TaskSnapshotEntity:
        return await self.retention_service.export_task(task_id)

    async def export_task_to_url(
        self,
        task_id: str,
        upload_url: str,
    ) -> TaskExportToUrlResultEntity:
        return await self.retention_service.export_task_to_url(
            task_id=task_id,
            upload_url=upload_url,
        )

    async def clean_task(
        self,
        task_id: str,
        force: bool = False,
        idle_days: int = 7,
    ) -> TaskCleanupResultEntity:
        """
        force=True is the admin escape hatch; it bypasses the idle-threshold
        check (but NOT the active-workflow / unprocessed-events checks, which
        protect correctness, not policy).
        """
        return await self.retention_service.clean_task(
            task_id=task_id,
            enforce_idle_threshold=not force,
            idle_days=idle_days,
        )

    async def rehydrate_task(
        self,
        task_id: str,
        snapshot: TaskSnapshotEntity | None = None,
        snapshot_url: str | None = None,
    ) -> None:
        await self.retention_service.rehydrate_task(
            task_id=task_id,
            snapshot=snapshot,
            snapshot_url=snapshot_url,
        )


DTaskRetentionUseCase = Annotated[TaskRetentionUseCase, Depends(TaskRetentionUseCase)]
