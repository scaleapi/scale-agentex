import builtins
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import and_, delete, or_, select, update
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import TaskMessageORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.task_messages import (
    TaskMessageEntity,
    TaskMessageEntityFilter,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

DEFAULT_PAGE_LIMIT = 50


def _flatten_to_dot_path(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dict to dot-separated paths."""
    result: dict[str, Any] = {}
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_to_dot_path(value, full_key))
        else:
            result[full_key] = value
    return result


def _build_jsonb_clause(field_path: str, value: Any):
    """
    Build a SQLAlchemy JSONB comparison clause for a dot-separated field path.

    e.g., "content.type" -> TaskMessageORM.content["type"].astext == value
    e.g., "content.data.type" -> TaskMessageORM.content["data"]["type"].astext == value
    """
    parts = field_path.split(".")
    if parts[0] == "content" and len(parts) > 1:
        # Navigate into the JSONB column
        col = TaskMessageORM.content
        for part in parts[1:]:
            col = col[part]
        return col.astext == str(value)

    # For non-JSONB fields, use direct column comparison
    if hasattr(TaskMessageORM, parts[0]):
        return getattr(TaskMessageORM, parts[0]) == value

    return None


def convert_filters_to_postgres_clauses(
    filters: list[TaskMessageEntityFilter],
) -> list:
    """
    Convert TaskMessageEntityFilter objects to SQLAlchemy WHERE clauses.

    Mirrors the MongoDB filter logic:
    - Inclusionary filters (exclude=False) are OR'd together
    - Exclusionary filters (exclude=True) are OR'd together and negated
    - The two groups are AND'd
    """
    if not filters:
        return []

    include_filters = [f for f in filters if not f.exclude]
    exclude_filters = [f for f in filters if f.exclude]

    clauses = []

    if include_filters:
        include_clauses = []
        for f in include_filters:
            data = f.model_dump(exclude_none=True, exclude={"exclude"})
            flat = _flatten_to_dot_path(data)
            filter_clauses = []
            for path, value in flat.items():
                clause = _build_jsonb_clause(path, value)
                if clause is not None:
                    filter_clauses.append(clause)
            if filter_clauses:
                include_clauses.append(and_(*filter_clauses))
        if include_clauses:
            clauses.append(or_(*include_clauses))

    if exclude_filters:
        exclude_clauses = []
        for f in exclude_filters:
            data = f.model_dump(exclude_none=True, exclude={"exclude"})
            flat = _flatten_to_dot_path(data)
            filter_clauses = []
            for path, value in flat.items():
                clause = _build_jsonb_clause(path, value)
                if clause is not None:
                    filter_clauses.append(clause)
            if filter_clauses:
                exclude_clauses.append(and_(*filter_clauses))
        if exclude_clauses:
            clauses.append(~or_(*exclude_clauses))

    return clauses


class TaskMessagePostgresRepository(
    PostgresCRUDRepository[TaskMessageORM, TaskMessageEntity]
):
    """Repository for managing task messages in PostgreSQL."""

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            TaskMessageORM,
            TaskMessageEntity,
        )

    async def update(self, item: TaskMessageEntity) -> TaskMessageEntity:
        """
        Update a task message using UPDATE ... RETURNING for single round-trip.
        """
        async with (
            self.start_async_db_session(allow_writes=True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskMessageORM)
                .where(TaskMessageORM.id == item.id)
                .values(**item.to_dict())
                .returning(TaskMessageORM)
            )
            result = await session.execute(stmt)
            await session.commit()
            updated_orm = result.scalar_one()
            return TaskMessageEntity.model_validate(updated_orm)

    async def find_by_field(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        page_number: int | None = None,
        sort_by: dict[str, int] | None = None,
        filters: list[TaskMessageEntityFilter] | None = None,
    ) -> builtins.list[TaskMessageEntity]:
        """
        Find messages by field with offset pagination and optional JSONB filters.
        """
        async with (
            self.start_async_db_session(allow_writes=False) as session,
            async_sql_exception_handler(),
        ):
            query = select(TaskMessageORM).where(
                getattr(TaskMessageORM, field_name) == field_value
            )

            # Apply JSONB filters
            if filters:
                filter_clauses = convert_filters_to_postgres_clauses(filters)
                for clause in filter_clauses:
                    query = query.where(clause)

            # Apply sorting
            if sort_by:
                from sqlalchemy import asc, desc

                for field, direction in sort_by.items():
                    if hasattr(TaskMessageORM, field):
                        col = getattr(TaskMessageORM, field)
                        query = query.order_by(
                            desc(col) if direction == -1 else asc(col)
                        )
            # Always use id as tiebreaker
            from sqlalchemy import asc as sa_asc

            query = query.order_by(sa_asc(TaskMessageORM.id))

            # Apply pagination
            limit = limit or DEFAULT_PAGE_LIMIT
            query = query.limit(limit)

            if page_number is not None and page_number >= 1:
                query = query.offset((page_number - 1) * limit)

            result = await session.execute(query)
            return [
                TaskMessageEntity.model_validate(row) for row in result.scalars().all()
            ]

    async def find_by_field_with_cursor(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        sort_by: dict[str, int] | None = None,
        before_id: str | None = None,
        after_id: str | None = None,
        filters: list[TaskMessageEntityFilter] | None = None,
    ) -> builtins.list[TaskMessageEntity]:
        """
        Find messages with cursor-based pagination using (created_at, id) compound comparison.
        """
        async with (
            self.start_async_db_session(allow_writes=False) as session,
            async_sql_exception_handler(),
        ):
            query = select(TaskMessageORM).where(
                getattr(TaskMessageORM, field_name) == field_value
            )

            # Apply JSONB filters
            if filters:
                filter_clauses = convert_filters_to_postgres_clauses(filters)
                for clause in filter_clauses:
                    query = query.where(clause)

            # Cursor pagination: look up cursor document's created_at
            if before_id or after_id:
                cursor_id = before_id or after_id
                cursor_query = select(TaskMessageORM.created_at).where(
                    TaskMessageORM.id == cursor_id
                )
                cursor_result = await session.execute(cursor_query)
                cursor_row = cursor_result.scalar_one_or_none()

                if cursor_row is not None:
                    cursor_timestamp = cursor_row
                    if before_id:
                        # For descending created_at, ascending id:
                        # Get documents with created_at < cursor OR
                        # (created_at == cursor AND id > cursor_id)
                        query = query.where(
                            or_(
                                TaskMessageORM.created_at < cursor_timestamp,
                                and_(
                                    TaskMessageORM.created_at == cursor_timestamp,
                                    TaskMessageORM.id > cursor_id,
                                ),
                            )
                        )
                    else:  # after_id
                        # Get documents with created_at > cursor OR
                        # (created_at == cursor AND id < cursor_id)
                        query = query.where(
                            or_(
                                TaskMessageORM.created_at > cursor_timestamp,
                                and_(
                                    TaskMessageORM.created_at == cursor_timestamp,
                                    TaskMessageORM.id < cursor_id,
                                ),
                            )
                        )

            # Apply sorting
            if sort_by:
                from sqlalchemy import asc, desc

                for field, direction in sort_by.items():
                    if hasattr(TaskMessageORM, field):
                        col = getattr(TaskMessageORM, field)
                        query = query.order_by(
                            desc(col) if direction == -1 else asc(col)
                        )
            # Always use id as tiebreaker
            from sqlalchemy import asc as sa_asc

            query = query.order_by(sa_asc(TaskMessageORM.id))

            # Apply limit
            limit = limit or DEFAULT_PAGE_LIMIT
            query = query.limit(limit)

            result = await session.execute(query)
            return [
                TaskMessageEntity.model_validate(row) for row in result.scalars().all()
            ]

    async def delete_by_field(self, field_name: str, field_value: Any) -> int:
        """Delete all messages matching a field value. Returns count deleted."""
        async with (
            self.start_async_db_session(allow_writes=True) as session,
            async_sql_exception_handler(),
        ):
            stmt = delete(TaskMessageORM).where(
                getattr(TaskMessageORM, field_name) == field_value
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[TaskMessageEntity]:
        """List messages with optional filtering and pagination."""
        return await super().list(
            filters=filters,
            order_by=order_by or "created_at",
            order_direction=order_direction or "desc",
            limit=limit,
            page_number=page_number,
        )


DTaskMessagePostgresRepository = Annotated[
    TaskMessagePostgresRepository, Depends(TaskMessagePostgresRepository)
]
