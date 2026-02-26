from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from src.adapters.crud_store.adapter_postgres import async_sql_exception_handler
from src.adapters.orm import CheckpointBlobORM, CheckpointORM, CheckpointWriteORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)


class CheckpointRepository:
    """Repository for LangGraph checkpoint operations.

    Uses raw SQLAlchemy queries because the checkpoint tables have
    composite primary keys that don't fit the generic CRUD repository.
    """

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        self.async_rw_session_maker = async_read_write_session_maker
        self.async_ro_session_maker = async_read_only_session_maker

    async def get_tuple(
        self,
        thread_id: str,
        checkpoint_ns: str = "",
        checkpoint_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch a checkpoint along with its blobs and pending writes.

        If checkpoint_id is None, returns the latest checkpoint for the thread/ns.
        """
        async with (
            self.async_ro_session_maker() as session,
            async_sql_exception_handler(),
        ):
            # Build checkpoint query
            query = select(CheckpointORM).where(
                CheckpointORM.thread_id == thread_id,
                CheckpointORM.checkpoint_ns == checkpoint_ns,
            )
            if checkpoint_id:
                query = query.where(CheckpointORM.checkpoint_id == checkpoint_id)
            else:
                query = query.order_by(CheckpointORM.checkpoint_id.desc()).limit(1)

            result = await session.execute(query)
            cp = result.scalar_one_or_none()
            if cp is None:
                return None

            # Fetch blobs whose (channel, version) appears in checkpoint.channel_versions
            channel_versions: dict[str, str] = cp.checkpoint.get("channel_versions", {})
            blobs: list[dict[str, Any]] = []
            if channel_versions:
                # Build OR conditions for each (channel, version) pair
                blob_query = select(CheckpointBlobORM).where(
                    CheckpointBlobORM.thread_id == thread_id,
                    CheckpointBlobORM.checkpoint_ns == checkpoint_ns,
                )
                # Filter to only matching channel+version pairs
                conditions = []
                for channel, version in channel_versions.items():
                    conditions.append(
                        (CheckpointBlobORM.channel == channel)
                        & (CheckpointBlobORM.version == str(version))
                    )
                if conditions:
                    blob_query = blob_query.where(or_(*conditions))

                blob_result = await session.execute(blob_query)
                for b in blob_result.scalars().all():
                    blobs.append(
                        {
                            "channel": b.channel,
                            "version": b.version,
                            "type": b.type,
                            "blob": bytes(b.blob) if b.blob is not None else None,
                        }
                    )

            # Fetch pending writes for this checkpoint
            writes_query = (
                select(CheckpointWriteORM)
                .where(
                    CheckpointWriteORM.thread_id == thread_id,
                    CheckpointWriteORM.checkpoint_ns == checkpoint_ns,
                    CheckpointWriteORM.checkpoint_id == cp.checkpoint_id,
                )
                .order_by(CheckpointWriteORM.task_id, CheckpointWriteORM.idx)
            )
            writes_result = await session.execute(writes_query)
            writes: list[dict[str, Any]] = []
            for w in writes_result.scalars().all():
                writes.append(
                    {
                        "task_id": w.task_id,
                        "idx": w.idx,
                        "channel": w.channel,
                        "type": w.type,
                        "blob": bytes(w.blob) if w.blob is not None else None,
                    }
                )

            return {
                "thread_id": cp.thread_id,
                "checkpoint_ns": cp.checkpoint_ns,
                "checkpoint_id": cp.checkpoint_id,
                "parent_checkpoint_id": cp.parent_checkpoint_id,
                "checkpoint": cp.checkpoint,
                "metadata": cp.metadata_,
                "blobs": blobs,
                "pending_writes": writes,
            }

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
        """Upsert a checkpoint and its blobs in one transaction."""
        async with (
            self.async_rw_session_maker() as session,
            async_sql_exception_handler(),
        ):
            # Upsert blobs
            for blob in blobs:
                stmt = (
                    insert(CheckpointBlobORM)
                    .values(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        channel=blob["channel"],
                        version=blob["version"],
                        type=blob["type"],
                        blob=blob.get("blob"),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "thread_id",
                            "checkpoint_ns",
                            "channel",
                            "version",
                        ]
                    )
                )
                await session.execute(stmt)

            # Upsert checkpoint
            stmt = (
                insert(CheckpointORM)
                .values(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=parent_checkpoint_id,
                    checkpoint=checkpoint,
                    metadata_=metadata,
                )
                .on_conflict_do_update(
                    index_elements=["thread_id", "checkpoint_ns", "checkpoint_id"],
                    set_={
                        "checkpoint": checkpoint,
                        "metadata": metadata,  # use DB column name, not Python attr
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def put_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        writes: list[dict[str, Any]],
        upsert: bool = False,
    ) -> None:
        """Batch insert/upsert checkpoint writes."""
        async with (
            self.async_rw_session_maker() as session,
            async_sql_exception_handler(),
        ):
            for w in writes:
                stmt = insert(CheckpointWriteORM).values(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    task_id=w["task_id"],
                    idx=w["idx"],
                    channel=w["channel"],
                    type=w.get("type"),
                    blob=w["blob"],
                    task_path=w.get("task_path", ""),
                )
                if upsert:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[
                            "thread_id",
                            "checkpoint_ns",
                            "checkpoint_id",
                            "task_id",
                            "idx",
                        ],
                        set_={
                            "channel": w["channel"],
                            "type": w.get("type"),
                            "blob": w["blob"],
                        },
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=[
                            "thread_id",
                            "checkpoint_ns",
                            "checkpoint_id",
                            "task_id",
                            "idx",
                        ],
                    )
                await session.execute(stmt)
            await session.commit()

    async def list_checkpoints(
        self,
        thread_id: str,
        checkpoint_ns: str | None = None,
        before_checkpoint_id: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List checkpoints matching criteria, ordered newest first."""
        async with (
            self.async_ro_session_maker() as session,
            async_sql_exception_handler(),
        ):
            query = select(CheckpointORM).where(
                CheckpointORM.thread_id == thread_id
            )

            if checkpoint_ns is not None:
                query = query.where(CheckpointORM.checkpoint_ns == checkpoint_ns)
            if before_checkpoint_id is not None:
                query = query.where(CheckpointORM.checkpoint_id < before_checkpoint_id)
            if filter_metadata:
                # JSONB containment operator @>
                query = query.where(CheckpointORM.metadata_.op("@>")(filter_metadata))

            query = query.order_by(CheckpointORM.checkpoint_id.desc())
            query = query.limit(limit)

            result = await session.execute(query)
            rows = result.scalars().all()

            checkpoints = []
            for cp in rows:
                # For list, include checkpoint + metadata but not full blobs/writes
                # to keep the response lightweight. Clients call get_tuple for full data.
                checkpoints.append(
                    {
                        "thread_id": cp.thread_id,
                        "checkpoint_ns": cp.checkpoint_ns,
                        "checkpoint_id": cp.checkpoint_id,
                        "parent_checkpoint_id": cp.parent_checkpoint_id,
                        "checkpoint": cp.checkpoint,
                        "metadata": cp.metadata_,
                    }
                )
            return checkpoints

    async def delete_thread(self, thread_id: str) -> None:
        """Delete all checkpoint data for a thread."""
        async with (
            self.async_rw_session_maker() as session,
            async_sql_exception_handler(),
        ):
            await session.execute(
                delete(CheckpointWriteORM).where(
                    CheckpointWriteORM.thread_id == thread_id
                )
            )
            await session.execute(
                delete(CheckpointBlobORM).where(
                    CheckpointBlobORM.thread_id == thread_id
                )
            )
            await session.execute(
                delete(CheckpointORM).where(CheckpointORM.thread_id == thread_id)
            )
            await session.commit()


DCheckpointRepository = Annotated[CheckpointRepository, Depends(CheckpointRepository)]
