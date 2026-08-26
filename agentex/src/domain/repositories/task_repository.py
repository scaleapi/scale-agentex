from collections.abc import Collection, Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy import and_, cast, distinct, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload
from src.adapters.crud_store.adapter_postgres import (
    ColumnPrimitiveValue,
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import AgentORM, AgentTaskTrackerORM, TaskAgentORM, TaskORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.tasks import (
    NON_TERMINAL_TASK_STATUSES,
    TaskEntity,
    TaskFailureSource,
    TaskRelationships,
    TaskStatus,
)
from src.domain.exceptions import ClientError
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskRepository(PostgresCRUDRepository[TaskORM, TaskEntity, TaskRelationships]):
    """Repository for Task entity with relationship loading support"""

    orm_class = TaskORM
    entity_class = TaskEntity
    relationships = TaskRelationships
    relationships_to_load_options = {
        TaskRelationships.AGENTS: selectinload(TaskORM.agents),
    }

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            TaskORM,
            TaskEntity,
        )

    async def list_with_join(
        self,
        *,
        task_filters: dict[str, ColumnPrimitiveValue | Sequence[ColumnPrimitiveValue]]
        | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        task_metadata: dict | None = None,
        order_by: str | None = None,
        order_direction: Literal["asc", "desc"] = "desc",
        limit: int | None = None,
        page_number: int | None = None,
        relationships: list[TaskRelationships] | None = None,
    ) -> list[TaskEntity]:
        """
        List Tasks with custom filters that may require joining tables.

        Args:
            - task_filters: Filters on the task table itself
            - agent_id: Filter tasks by agent ID using the join table
            - agent_name: Filter tasks by agent name
            - task_metadata: JSONB containment filter on `task_metadata`. Returns
              tasks whose metadata is a JSON superset of the provided dict.
            - order_by: Column to order by
            - order_direction: Direction to order by
            - limit: Maximum number of results to return
            - page_number: Page number to return
            - relationships: List of relationships to eagerly load (e.g., [TaskRelationships.AGENTS])
        """

        query = select(TaskORM)
        if agent_id or agent_name:
            query = query.join(TaskAgentORM, TaskORM.id == TaskAgentORM.task_id)
            if agent_name:
                query = query.join(
                    AgentORM, TaskAgentORM.agent_id == AgentORM.id
                ).where(AgentORM.name == agent_name)
            if agent_id:
                query = query.where(TaskAgentORM.agent_id == agent_id)
        if task_metadata is not None:
            query = query.where(TaskORM.task_metadata.contains(task_metadata))
        query = query.where(TaskORM.status != TaskStatus.DELETED)
        return await self.list(
            filters=task_filters,
            order_by=order_by,
            order_direction=order_direction,
            query=query,
            limit=limit,
            page_number=page_number,
            relationships=relationships,
        )

    async def list_cleanup_candidate_ids(
        self,
        *,
        idle_days: int,
        agent_names: Sequence[str],
        after_id: str | None,
        limit: int,
    ) -> list[str]:
        """
        Return ids of tasks eligible for scheduled retention cleanup.

        Cheap, index-friendly PRE-FILTER only — the authoritative idle / status /
        unprocessed-events checks live in TaskRetentionService.clean_task. This
        deliberately omits a status filter: status is race-prone (a task can flip
        to RUNNING between this query and the clean call), so the trustworthy
        RUNNING guard is enforced at clean-time. `updated_at < cutoff` is a correct
        superset of truly-idle tasks (true idleness also requires the latest Mongo
        message to predate the cutoff), so we never under-include.

        Keyset-paginated by id ascending; pass the last returned id as `after_id`
        to fetch the next page. Fail-closed: empty `agent_names` returns [].
        """
        if not agent_names:
            return []

        cutoff = datetime.now(UTC) - timedelta(days=idle_days)
        query = (
            select(TaskORM.id)
            .join(TaskAgentORM, TaskORM.id == TaskAgentORM.task_id)
            .join(AgentORM, TaskAgentORM.agent_id == AgentORM.id)
            .where(
                TaskORM.cleaned_at.is_(None),
                TaskORM.updated_at < cutoff,
                AgentORM.name.in_(agent_names),
            )
            .order_by(TaskORM.id.asc())
            .limit(limit)
            .distinct()
        )
        if after_id is not None:
            query = query.where(TaskORM.id > after_id)

        async with self.start_async_db_session(allow_writes=False) as session:
            result = await session.execute(query)
            return [row[0] for row in result.all()]

    async def list_multi_agent_task_ids(self, *, task_ids: Sequence[str]) -> list[str]:
        """
        Return task IDs from the provided candidate set that are linked to >1 agent.

        Scheduled cleanup is task-wide, so multi-agent tasks are skipped by the
        sweep even when one associated agent is allowlisted.
        """
        if not task_ids:
            return []

        query = (
            select(TaskAgentORM.task_id)
            .where(TaskAgentORM.task_id.in_(task_ids))
            .group_by(TaskAgentORM.task_id)
            .having(func.count(distinct(TaskAgentORM.agent_id)) > 1)
            .order_by(TaskAgentORM.task_id.asc())
        )

        async with self.start_async_db_session(allow_writes=False) as session:
            result = await session.execute(query)
            return [row[0] for row in result.all()]

    async def create(self, agent_id: str, task: TaskEntity) -> TaskEntity:
        """Create task and establish agent relationships"""

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            task_data = task.to_dict()
            # failure_source is deliberately excluded from public/domain
            # serialization, but the repository still persists it.
            task_data["failure_source"] = (
                task.failure_source.value if task.failure_source is not None else None
            )

            orm = self.orm(**task_data)
            session.add(orm)
            await session.flush()  # Get the task ID

            # Add agent relationships
            task_agent = TaskAgentORM(task_id=orm.id, agent_id=agent_id)
            session.add(task_agent)

            # Create a new agent task tracker
            agent_task_tracker = AgentTaskTrackerORM(
                agent_id=agent_id,
                task_id=orm.id,
                last_processed_event_id=None,
                status=None,
                status_reason=None,
            )
            session.add(agent_task_tracker)
            await session.commit()
            await session.refresh(orm)

            # Return with agents populated
            return TaskEntity.model_validate(orm)

    async def update(self, task: TaskEntity) -> TaskEntity:
        """Versioned whole-entity update, preserving agent relationships.

        Callers must supply the ``updated_at`` value they read. This keeps the
        legacy update surface from replaying stale task status or internal
        failure provenance over a concurrent lifecycle transition.
        """

        if task.updated_at is None:
            raise ClientError(
                f"Task {task.id} cannot be updated without an updated_at version"
            )

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Update task columns only (not relationships or database-managed
            # timestamps). ``failure_source`` is excluded from normal entity
            # serialization, so include it explicitly in the versioned write.
            task_data = task.to_dict(
                exclude={"id", "created_at", "updated_at", "agents"}
            )
            task_data["failure_source"] = (
                task.failure_source.value if task.failure_source is not None else None
            )

            stmt = (
                update(TaskORM)
                .where(
                    TaskORM.id == task.id,
                    TaskORM.updated_at == task.updated_at,
                )
                .values(**task_data)
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            modified_orm = result.scalar_one_or_none()
            await session.commit()
            if modified_orm is None:
                raise ClientError(
                    f"Task {task.id} was concurrently modified. Please retry the request."
                )
            return TaskEntity.model_validate(modified_orm)

    async def get_current(
        self,
        task_id: str | None = None,
        name: str | None = None,
        relationships: list[TaskRelationships] | None = None,
    ) -> TaskEntity:
        """Read the current task from the primary database."""
        async with (
            self.start_async_db_session(allow_writes=True) as session,
            async_sql_exception_handler(),
        ):
            task = await self._get(
                session,
                id=task_id,
                name=name,
                relationships=relationships,
            )
            return TaskEntity.model_validate(task)

    async def claim_acp_forward(self, task_id: str) -> TaskEntity | None:
        """Atomically claim a task for an ACP create call.

        Non-terminal tasks remain retryable. A FAILED task is eligible only when
        the prior failure was written by this forwarding path. The marker remains
        stable across column-scoped metadata writes, unlike the row timestamp.
        """
        eligible_status = or_(
            TaskORM.status.in_(NON_TERMINAL_TASK_STATUSES),
            and_(
                TaskORM.status == TaskStatus.FAILED,
                TaskORM.failure_source == TaskFailureSource.ACP_FORWARD.value,
            ),
        )
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskORM)
                .where(TaskORM.id == task_id, eligible_status)
                .values(
                    status=TaskStatus.RUNNING,
                    status_reason="Forwarding task to ACP server",
                    failure_source=TaskFailureSource.ACP_FORWARD.value,
                )
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            if row is None:
                return None
            return TaskEntity.model_validate(row)

    async def replace_metadata(
        self,
        task_id: str,
        task_metadata: dict | None,
    ) -> TaskEntity | None:
        """Replace only task metadata without replaying a stale task entity."""
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskORM)
                .where(TaskORM.id == task_id)
                .values(task_metadata=task_metadata)
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            if row is None:
                return None
            return TaskEntity.model_validate(row)

    async def set_cleaned_at(
        self,
        task_id: str,
        cleaned_at: datetime | None,
    ) -> TaskEntity | None:
        """Set only the retention marker, preserving concurrent lifecycle state."""
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskORM)
                .where(TaskORM.id == task_id)
                .values(cleaned_at=cleaned_at)
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            if row is None:
                return None
            return TaskEntity.model_validate(row)

    async def replace_params(
        self, task_id: str, params: dict | None
    ) -> TaskEntity | None:
        """Replace only a task's ``params`` and return the current entity.

        The single-column update prevents a stale caller from overwriting status
        or other fields that changed after it read the task.
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskORM)
                .where(TaskORM.id == task_id)
                .values(params=params)
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            if row is None:
                return None
            return TaskEntity.model_validate(row)

    async def merge_params(self, task_id: str, patch: dict) -> TaskEntity | None:
        """Atomically shallow-merge ``patch`` into the task's ``params``
        JSONB column. Returns the updated entity, or ``None`` if no task
        with that id exists.

        Uses Postgres' ``||`` operator on JSONB so the read-modify-write
        is collapsed to a single statement (no race with concurrent
        writers). ``patch`` keys overwrite existing keys at the top
        level; nested objects are NOT deep-merged — pass the full nested
        replacement if you need to change a subfield.

        Intended for surfaces that need ``tasks.params`` to reflect the
        latest agent config after a live edit (see
        ``TasksUseCase.update_mutable_fields_on_task``); not a
        general-purpose updater.
        """

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # ``COALESCE(params, '{}'::jsonb)`` so a NULL existing value
            # doesn't poison the concat to NULL. Both operands cast to
            # JSONB explicitly so Postgres picks the JSONB ``||`` operator
            # (not the text concat overload).
            existing = func.coalesce(TaskORM.params, cast({}, JSONB))
            merged = existing.op("||", return_type=JSONB)(cast(patch, JSONB))
            stmt = (
                update(TaskORM)
                .where(TaskORM.id == task_id)
                .values(params=merged)
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            if row is None:
                return None
            return TaskEntity.model_validate(row)

    async def transition_status(
        self,
        task_id: str,
        expected_status: TaskStatus | Collection[TaskStatus],
        new_status: TaskStatus,
        status_reason: str,
        task_metadata: dict | None = None,
        expected_updated_at: datetime | None = None,
        expected_failure_source: TaskFailureSource | None = None,
        new_failure_source: TaskFailureSource | None = None,
    ) -> TaskEntity | None:
        """Atomically transition from eligible status/version state."""

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            values: dict = {
                "status": new_status,
                "status_reason": status_reason,
                # Every ordinary status transition takes ownership away from a
                # prior ACP forwarding failure unless the caller explicitly
                # records a new one.
                "failure_source": (
                    new_failure_source.value if new_failure_source is not None else None
                ),
            }
            if task_metadata is not None:
                values["task_metadata"] = task_metadata

            status_filter = (
                TaskORM.status == expected_status
                if isinstance(expected_status, TaskStatus)
                else TaskORM.status.in_(expected_status)
            )
            filters = [TaskORM.id == task_id, status_filter]
            if expected_updated_at is not None:
                filters.append(TaskORM.updated_at == expected_updated_at)
            if expected_failure_source is not None:
                filters.append(TaskORM.failure_source == expected_failure_source.value)

            stmt = update(TaskORM).where(*filters).values(**values)
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount == 0:
                return None

            refreshed = await session.get(TaskORM, task_id)
            if refreshed is None:
                return None
            return TaskEntity.model_validate(refreshed)

    async def transition_to_terminal_status(
        self,
        *,
        task_id: str | None,
        name: str | None,
        new_status: TaskStatus,
        status_reason: str,
        include_acp_forward_failure: bool,
    ) -> TaskEntity | None:
        """Atomically take terminal ownership from every eligible live state.

        The predicate is evaluated by PostgreSQL in the same statement as the
        write. A workflow terminal transition therefore wins whether an ACP
        retry is still FAILED, has claimed RUNNING, or has just confirmed the
        forward. Clearing ``failure_source`` in that statement prevents any
        later stale retry CAS from reviving the task.
        """
        if task_id is None and name is None:
            raise ClientError("Either task_id or name must be provided")

        identifier_filter = (
            TaskORM.id == task_id if task_id is not None else TaskORM.name == name
        )
        eligible_status = TaskORM.status.in_(NON_TERMINAL_TASK_STATUSES)
        if include_acp_forward_failure:
            eligible_status = or_(
                eligible_status,
                and_(
                    TaskORM.status == TaskStatus.FAILED,
                    TaskORM.failure_source == TaskFailureSource.ACP_FORWARD.value,
                ),
            )

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskORM)
                .where(identifier_filter, eligible_status)
                .values(
                    status=new_status,
                    status_reason=status_reason,
                    failure_source=None,
                )
                .returning(TaskORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            await session.commit()
            if row is None:
                return None
            return TaskEntity.model_validate(row)


DTaskRepository = Annotated[TaskRepository, Depends(TaskRepository)]
