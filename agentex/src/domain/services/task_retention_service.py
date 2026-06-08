"""
TaskRetentionService — exports, cleans, and rehydrates task content.

The same service methods back both the HTTP endpoints (admin / external
caller integration) and the Temporal cleanup activity (scheduled sweep).
Domain logic lives here; api/routes/ and src/temporal/ are thin wrappers.

Cross-database operation ordering (see clean_task for details):
- Mongo deletes first (each delete-by-task-id is naturally idempotent).
- Postgres transaction last (carries the cleaned_at marker that gates re-cleaning).
- Temporal workflow termination outside the DB transaction (best-effort; history
  retention will eventually expire it anyway).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends

from src.adapters.temporal.adapter_temporal import DTemporalAdapter
from src.config.dependencies import DHttpxClient
from src.domain.entities.task_retention import (
    TaskCleanupResultEntity,
    TaskExportToUrlResultEntity,
    TaskSnapshotEntity,
)
from src.domain.entities.tasks import TaskStatus
from src.domain.exceptions import ClientError, ServiceError
from src.domain.repositories.agent_task_tracker_repository import (
    DAgentTaskTrackerRepository,
)
from src.domain.repositories.event_repository import DEventRepository
from src.domain.repositories.task_message_repository import DTaskMessageRepository
from src.domain.repositories.task_repository import DTaskRepository
from src.domain.repositories.task_state_repository import DTaskStateRepository
from src.domain.services.task_message_service import DTaskMessageService
from src.utils.logging import make_logger
from src.utils.url_validation import validate_external_url

logger = make_logger(__name__)

# Page size for paginated reads during export. Big enough to make most tasks
# fit in a single round-trip; small enough that a single oversized task can't
# blow the request budget. Revisit if export latency becomes an issue.
EXPORT_PAGE_SIZE = 500


class TaskRetentionService:
    def __init__(
        self,
        task_repository: DTaskRepository,
        task_message_service: DTaskMessageService,
        task_message_repository: DTaskMessageRepository,
        task_state_repository: DTaskStateRepository,
        event_repository: DEventRepository,
        agent_task_tracker_repository: DAgentTaskTrackerRepository,
        temporal_adapter: DTemporalAdapter,
        httpx_client: DHttpxClient,
    ):
        self.task_repository = task_repository
        self.task_message_service = task_message_service
        self.task_message_repository = task_message_repository
        self.task_state_repository = task_state_repository
        self.event_repository = event_repository
        self.agent_task_tracker_repository = agent_task_tracker_repository
        self.temporal_adapter = temporal_adapter
        self.httpx_client = httpx_client

    async def export_task(self, task_id: str) -> TaskSnapshotEntity:
        """
        Build a self-contained snapshot of all content-bearing rows for a task.

        Works for both active and cleaned tasks:
        - Active: returns current live state (useful for debugging, ops snapshots).
        - Cleaned: returns the (empty) state — primarily a no-op safety check that
          tells the caller "nothing to export."

        Raises if the task does not exist.
        """
        # 1. Load the task. task_repository.get raises if missing.
        await self.task_repository.get(id=task_id)

        # 2. Page through messages, ordered chronologically so the snapshot
        #    replays cleanly on rehydrate. Pagination is 1-based in this codebase.
        messages = []
        page_number = 1
        while True:
            page = await self.task_message_service.get_messages(
                task_id=task_id,
                limit=EXPORT_PAGE_SIZE,
                page_number=page_number,
                order_by="created_at",
                order_direction="asc",
            )
            messages.extend(page)
            if len(page) < EXPORT_PAGE_SIZE:
                break
            page_number += 1

        # 3. Page through task_states.
        task_states = []
        page_number = 1
        while True:
            page = await self.task_state_repository.find_by_field(
                "task_id",
                task_id,
                limit=EXPORT_PAGE_SIZE,
                page_number=page_number,
                sort_by={"created_at": 1},
            )
            task_states.extend(page)
            if len(page) < EXPORT_PAGE_SIZE:
                break
            page_number += 1

        return TaskSnapshotEntity(
            task_id=task_id,
            messages=messages,
            task_states=task_states,
        )

    async def export_task_to_url(
        self,
        task_id: str,
        upload_url: str,
    ) -> TaskExportToUrlResultEntity:
        """
        Build the snapshot the same way export_task does, then PUT the JSON
        body to a caller-supplied presigned URL. Useful when the snapshot is
        too large to fit comfortably in a JSON response body.

        The upload URL is validated against the SSRF guard before any request
        is issued (see utils.url_validation).
        """
        await validate_external_url(upload_url)

        snapshot = await self.export_task(task_id)
        body = snapshot.model_dump_json().encode("utf-8")

        try:
            response = await self.httpx_client.put(
                upload_url,
                content=body,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except Exception as e:
            raise ServiceError(
                message=f"Failed to upload snapshot for task {task_id}",
                detail=str(e),
            ) from e

        result = TaskExportToUrlResultEntity(
            task_id=task_id,
            upload_url=upload_url,
            uploaded_bytes=len(body),
            messages_count=len(snapshot.messages),
            task_states_count=len(snapshot.task_states),
        )

        logger.info(
            "task_export_to_url_completed",
            extra={
                "task_id": result.task_id,
                "upload_url": result.upload_url,
                "uploaded_bytes": result.uploaded_bytes,
                "messages_count": result.messages_count,
                "task_states_count": result.task_states_count,
            },
        )

        return result

    async def clean_task(
        self,
        task_id: str,
        *,
        enforce_idle_threshold: bool = True,
        idle_days: int = 7,
    ) -> TaskCleanupResultEntity:
        """
        Delete content-bearing rows for a stale task. Idempotent: re-running on a
        partially-cleaned or fully-cleaned task is safe.

        Args:
            task_id: The task to clean.
            enforce_idle_threshold: When True (default), refuses to clean a task
                whose last interaction is more recent than `idle_days`. The
                scheduled Temporal sweep always sets True. The admin endpoint
                accepts a force=true flag that flips this to False.
            idle_days: Idle threshold in days (when enforce_idle_threshold=True).

        Refuses (raises) if:
        - task is currently active (status == RUNNING).
        - enforce_idle_threshold=True and the task is not idle long enough.
        - unprocessed events exist past agent_task_tracker cursors.

        If cleaned_at IS NOT NULL (already cleaned), returns an empty result
        (zero rows deleted) rather than raising.

        Returns the result record describing what was deleted; the same record
        is emitted as a structured log line for forensics.

        ORDER OF OPERATIONS (load-bearing for retry safety):
        1. Reload task fresh. Bail with empty-result if cleaned_at is set.
        2. Verify task status and (if enforced) idle threshold.
        3. Verify no events past agent_task_tracker.last_processed_event_id.
           OPTIMISTIC: no row locks. Race window: a new EVENT_SEND between
           this check and step 6c will be deleted with the rest. Acceptable
           because (a) it can only happen on a task that's been idle ≥7d and
           then suddenly receives an event — rare; (b) the structured log
           below surfaces any cleanup with events_deleted > 0 on an
           idle-checked task, giving forensic signal.
        4. Mongo: delete messages by task_id (idempotent).
        5. Mongo: delete task_states by task_id (idempotent).
        6. Postgres (separate operations, each idempotent):
           a. delete events by task_id
           b. reset agent_task_tracker cursors for task_id
           c. update tasks.cleaned_at = now()
        7. Emit structured log with the TaskCleanupResultEntity payload.

        Note on Temporal workflows: Agentex doesn't own workflow IDs for agent
        tasks (the agent's ACP server creates them). By the time a task is
        idle ≥7d, any associated workflow should already be terminal.
        The active-status guard in step 2 catches the case where it isn't.
        """
        # 1. Reload task; bail if already cleaned.
        task = await self.task_repository.get(id=task_id)
        if task.cleaned_at is not None:
            return TaskCleanupResultEntity(
                task_id=task_id,
                cleaned_at=task.cleaned_at,
                messages_deleted=0,
                task_states_deleted=0,
                events_deleted=0,
            )

        # 2. Status + idle threshold guards.
        if task.status == TaskStatus.RUNNING:
            raise ClientError(
                f"Cannot clean task {task_id}: status is RUNNING (active)"
            )
        if enforce_idle_threshold and not await self._is_task_idle(task, idle_days):
            raise ClientError(
                f"Cannot clean task {task_id}: not idle for {idle_days} days "
                f"(use force=true to override)"
            )

        # 3. Unprocessed-events guard.
        if await self._has_unprocessed_events(task_id):
            raise ClientError(f"Cannot clean task {task_id}: unprocessed events remain")

        # 4-5. Mongo deletes.
        messages_deleted = await self.task_message_service.delete_all_messages(task_id)
        task_states_deleted = await self.task_state_repository.delete_by_field(
            "task_id", task_id
        )

        # 6a-b. Postgres deletes / resets.
        events_deleted = await self.event_repository.delete_by_task_id(task_id)
        await self.agent_task_tracker_repository.reset_cursors_for_task(task_id)

        # 6c. Mark task as cleaned.
        cleaned_at = datetime.now(UTC)
        task.cleaned_at = cleaned_at
        await self.task_repository.update(task)

        result = TaskCleanupResultEntity(
            task_id=task_id,
            cleaned_at=cleaned_at,
            messages_deleted=messages_deleted,
            task_states_deleted=task_states_deleted,
            events_deleted=events_deleted,
        )

        # 7. Forensic log line. Structured extras so Datadog can facet on them.
        logger.info(
            "task_cleanup_completed",
            extra={
                "task_id": result.task_id,
                "cleaned_at": result.cleaned_at.isoformat(),
                "messages_deleted": result.messages_deleted,
                "task_states_deleted": result.task_states_deleted,
                "events_deleted": result.events_deleted,
            },
        )

        return result

    async def preview_clean_task(
        self,
        task_id: str,
        *,
        enforce_idle_threshold: bool = True,
        idle_days: int = 7,
    ) -> TaskCleanupResultEntity:
        """
        Run the same safety checks as clean_task without deleting or updating data.

        This supports scheduled cleanup dry-runs in deployed environments: operators
        can confirm which tasks would pass the final deletion guards before enabling
        writes. The returned counts are intentionally zero because no write was
        attempted.
        """
        task = await self.task_repository.get(id=task_id)
        if task.cleaned_at is not None:
            cleaned_at = task.cleaned_at
        else:
            if task.status == TaskStatus.RUNNING:
                raise ClientError(
                    f"Cannot clean task {task_id}: status is RUNNING (active)"
                )
            if enforce_idle_threshold and not await self._is_task_idle(task, idle_days):
                raise ClientError(
                    f"Cannot clean task {task_id}: not idle for {idle_days} days "
                    f"(use force=true to override)"
                )
            if await self._has_unprocessed_events(task_id):
                raise ClientError(
                    f"Cannot clean task {task_id}: unprocessed events remain"
                )
            cleaned_at = datetime.now(UTC)

        result = TaskCleanupResultEntity(
            task_id=task_id,
            cleaned_at=cleaned_at,
            messages_deleted=0,
            task_states_deleted=0,
            events_deleted=0,
        )
        logger.info(
            "task_cleanup_dry_run_completed",
            extra={
                "task_id": result.task_id,
                "checked_at": result.cleaned_at.isoformat(),
            },
        )
        return result

    async def rehydrate_task(
        self,
        task_id: str,
        snapshot: TaskSnapshotEntity | None = None,
        snapshot_url: str | None = None,
    ) -> None:
        """
        Restore content-bearing rows from a snapshot. Inverse of clean_task.

        Source of the snapshot is mutually exclusive: caller supplies either an
        inline `snapshot` or a `snapshot_url` (presigned GET URL whose body is
        the JSON-encoded snapshot). URL form is for cases where the snapshot is
        larger than is comfortable as a JSON request body.

        Refuses (raises) if:
        - both/neither of snapshot and snapshot_url are provided.
        - snapshot.task_id != task_id (catch payload misuse).
        - cleaned_at IS NULL on the task (would clobber live data).
        - any supplied message.id or task_state.id already exists in Mongo
          (collision → DuplicateItemError surfaced from the adapter).

        Order of operations (mirror of clean_task):
        0. If snapshot_url is set, validate (SSRF) and download → parse to
           TaskSnapshotEntity.
        1. Reload task; verify cleaned_at IS NOT NULL.
        2. Mongo: batch insert messages with caller-supplied IDs.
        3. Mongo: batch insert task_states with caller-supplied IDs.
        4. Postgres: update tasks set cleaned_at = NULL.
           (Events are not restored; cursors stay NULL from clean_task.
           tasks.params is not touched — out of scope for v1.)

        Partial-insert hazard: insert_many is ordered, so a duplicate ID in
        the middle of the batch leaves prior inserts committed. Acceptable
        for v1 — the typical "double rehydrate" case has the collision in
        position 0 (no prior commits). Operators can recover by manually
        deleting the partial inserts and retrying.

        Note: ID preservation requires the caller to capture original Agentex IDs
        at write time and store them alongside content in their external system.
        This is a contract on the caller's integration, not enforced by Agentex.
        """
        if (snapshot is None) == (snapshot_url is None):
            raise ClientError("Provide exactly one of snapshot or snapshot_url.")

        if snapshot_url is not None:
            await validate_external_url(snapshot_url)
            try:
                response = await self.httpx_client.get(snapshot_url)
                response.raise_for_status()
            except Exception as e:
                raise ServiceError(
                    message=f"Failed to download snapshot from URL for task {task_id}",
                    detail=str(e),
                ) from e
            try:
                snapshot = TaskSnapshotEntity.model_validate_json(response.content)
            except Exception as e:
                raise ClientError(
                    f"Downloaded snapshot is not a valid TaskSnapshotEntity: {e}"
                ) from e

        # Validate payload before touching anything.
        if snapshot.task_id != task_id:
            raise ClientError(
                f"Snapshot task_id ({snapshot.task_id}) does not match "
                f"path task_id ({task_id})"
            )

        # Reject any embedded entity whose task_id disagrees with the path.
        # Mongo has no foreign key to tasks, so an unchecked batch_create here
        # would write rows that get tagged to a task the caller may not own.
        for i, message in enumerate(snapshot.messages):
            if message.task_id != task_id:
                raise ClientError(
                    f"Snapshot message[{i}] task_id ({message.task_id}) does not "
                    f"match path task_id ({task_id})"
                )
        for i, state in enumerate(snapshot.task_states):
            if state.task_id != task_id:
                raise ClientError(
                    f"Snapshot task_states[{i}] task_id ({state.task_id}) does "
                    f"not match path task_id ({task_id})"
                )

        # 1. Reload task; refuse if not in cleaned state.
        task = await self.task_repository.get(id=task_id)
        if task.cleaned_at is None:
            raise ClientError(
                f"Cannot rehydrate task {task_id}: task is not in cleaned state "
                f"(cleaned_at is NULL)"
            )

        # 2. Insert messages with caller-supplied IDs.
        if snapshot.messages:
            await self.task_message_repository.batch_create(snapshot.messages)

        # 3. Insert task_states with caller-supplied IDs.
        if snapshot.task_states:
            await self.task_state_repository.batch_create(snapshot.task_states)

        # 4. Clear cleaned_at on the task row.
        task.cleaned_at = None
        await self.task_repository.update(task)

        logger.info(
            "task_rehydrate_completed",
            extra={
                "task_id": task_id,
                "messages_restored": len(snapshot.messages),
                "task_states_restored": len(snapshot.task_states),
            },
        )

    # ---- internal helpers ----

    async def _is_task_idle(self, task, idle_days: int) -> bool:
        """
        True iff the task has no interaction within the idle window.

        Last-interaction = max(task.updated_at, latest message created_at).
        `task.updated_at` alone would miss tasks where the only recent
        activity is Mongo message writes (which don't bump the Postgres row).
        """
        cutoff = datetime.now(UTC) - timedelta(days=idle_days)
        last_interaction = task.updated_at

        latest_messages = await self.task_message_service.get_messages(
            task_id=task.id,
            limit=1,
            page_number=1,
            order_by="created_at",
            order_direction="desc",
        )
        if latest_messages and latest_messages[0].created_at is not None:
            # Mongo timestamps come back as naive datetimes; treat as UTC so
            # they compare cleanly with Postgres TIMESTAMPTZ values.
            latest_at = latest_messages[0].created_at
            if latest_at.tzinfo is None:
                latest_at = latest_at.replace(tzinfo=UTC)
            if last_interaction is None or latest_at > last_interaction:
                last_interaction = latest_at

        if last_interaction is None:
            return True
        return last_interaction < cutoff

    async def _has_unprocessed_events(self, task_id: str) -> bool:
        """
        True iff any events exist past agent_task_tracker.last_processed_event_id
        for any (task, agent) pair tied to this task.
        """
        trackers = await self.agent_task_tracker_repository.find_by_field(
            "task_id", task_id
        )
        for tracker in trackers:
            pending = await self.event_repository.list_events_after_last_processed(
                task_id=task_id,
                agent_id=tracker.agent_id,
                last_processed_event_id=tracker.last_processed_event_id,
                limit=1,
            )
            if pending:
                return True
        return False


DTaskRetentionService = Annotated[TaskRetentionService, Depends(TaskRetentionService)]
