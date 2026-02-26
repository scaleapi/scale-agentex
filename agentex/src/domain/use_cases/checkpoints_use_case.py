from typing import Annotated, Any

from fastapi import Depends

from src.domain.repositories.checkpoint_repository import DCheckpointRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)


class CheckpointsUseCase:
    def __init__(self, checkpoint_repository: DCheckpointRepository):
        self.checkpoint_repository = checkpoint_repository

    async def get_tuple(
        self,
        thread_id: str,
        checkpoint_ns: str = "",
        checkpoint_id: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.checkpoint_repository.get_tuple(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
        )

    async def put(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        parent_checkpoint_id: str | None,
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        blobs: list[dict[str, Any]],
    ) -> None:
        await self.checkpoint_repository.put(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint=checkpoint,
            metadata=metadata,
            blobs=blobs,
        )

    async def put_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        writes: list[dict[str, Any]],
        upsert: bool = False,
    ) -> None:
        await self.checkpoint_repository.put_writes(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
            writes=writes,
            upsert=upsert,
        )

    async def list_checkpoints(
        self,
        thread_id: str,
        checkpoint_ns: str | None = None,
        before_checkpoint_id: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await self.checkpoint_repository.list_checkpoints(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            before_checkpoint_id=before_checkpoint_id,
            filter_metadata=filter_metadata,
            limit=limit,
        )

    async def delete_thread(self, thread_id: str) -> None:
        await self.checkpoint_repository.delete_thread(thread_id=thread_id)


DCheckpointsUseCase = Annotated[CheckpointsUseCase, Depends(CheckpointsUseCase)]
