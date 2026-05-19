from typing import Annotated

from fastapi import Depends

from src.domain.entities.task_retention import (
    TaskCleanupResultEntity,
    TaskSnapshotEntity,
)
from src.domain.services.task_retention_service import DTaskRetentionService


class TaskRetentionUseCase:
    """
    Orchestrates export / clean / rehydrate operations for retention compliance.
    Backs both the HTTP admin endpoints and the Temporal scheduled cleanup
    activity; keep this layer thin so both callers exercise identical logic.
    """

    def __init__(self, retention_service: DTaskRetentionService):
        self.retention_service = retention_service

    async def export_task(self, task_id: str) -> TaskSnapshotEntity:
        return await self.retention_service.export_task(task_id)

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
        snapshot: TaskSnapshotEntity,
    ) -> None:
        await self.retention_service.rehydrate_task(
            task_id=task_id,
            snapshot=snapshot,
        )


DTaskRetentionUseCase = Annotated[TaskRetentionUseCase, Depends(TaskRetentionUseCase)]
