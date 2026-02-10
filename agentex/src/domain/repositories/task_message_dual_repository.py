# Note: List is used instead of list because the class has a method named 'list'
# which shadows the builtin in the class body for type annotations
from typing import Annotated, Any, List, Literal  # noqa: UP035

from datadog import statsd
from fastapi import Depends, Query
from src.config.dependencies import DEnvironmentVariables
from src.domain.entities.task_messages import (
    TaskMessageEntity,
    TaskMessageEntityFilter,
)
from src.domain.repositories.task_message_postgres_repository import (
    DTaskMessagePostgresRepository,
)
from src.domain.repositories.task_message_repository import (
    DTaskMessageRepository,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

TaskMessageStoragePhase = Literal["mongodb", "dual_write", "dual_read", "postgres"]


def _flatten_to_dot_notation(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dict to dot notation for MongoDB queries."""
    result: dict[str, Any] = {}
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_to_dot_notation(value, full_key))
        else:
            result[full_key] = value
    return result


def _convert_single_filter(filter_obj: TaskMessageEntityFilter) -> dict[str, Any]:
    """Convert a single filter to MongoDB query dict, excluding the 'exclude' field."""
    data = filter_obj.model_dump(exclude_none=True, exclude={"exclude"})
    return _flatten_to_dot_notation(data)


def _convert_filters_to_mongodb_query(
    filters: list[TaskMessageEntityFilter],
) -> dict[str, Any]:
    """Convert TaskMessageEntityFilter list to MongoDB query dict."""
    if not filters:
        return {}

    include_filters = [f for f in filters if not f.exclude]
    exclude_filters = [f for f in filters if f.exclude]

    include_query: dict[str, Any] | None = None
    exclude_query: dict[str, Any] | None = None

    if include_filters:
        converted = [_convert_single_filter(f) for f in include_filters]
        include_query = {"$or": converted}

    if exclude_filters:
        converted = [_convert_single_filter(f) for f in exclude_filters]
        exclude_query = {"$nor": converted}

    if include_query and exclude_query:
        return {"$and": [include_query, exclude_query]}
    elif include_query:
        return include_query
    elif exclude_query:
        return exclude_query
    else:
        return {}


# Metric names for dual-read verification
METRIC_DUAL_READ_MATCH = "task_message.dual_read.match"
METRIC_DUAL_READ_MISSING_POSTGRES = "task_message.dual_read.mismatch.missing_postgres"
METRIC_DUAL_READ_MISSING_MONGODB = "task_message.dual_read.mismatch.missing_mongodb"
METRIC_DUAL_READ_CONTENT_MISMATCH = "task_message.dual_read.mismatch.content"
METRIC_DUAL_READ_LIST_COUNT_MISMATCH = "task_message.dual_read.list_count_mismatch"


class TaskMessageDualRepository:
    """
    Dual-write repository that manages task message storage across MongoDB and PostgreSQL.

    Phases:
    - mongodb: Read/write only MongoDB (legacy behavior)
    - dual_write: Write to both, read from MongoDB
    - dual_read: Write to both, read from both (verify consistency)
    - postgres: Read/write only PostgreSQL (target state)
    """

    def __init__(
        self,
        mongo_repository: DTaskMessageRepository,
        postgres_repository: DTaskMessagePostgresRepository,
        environment_variables: DEnvironmentVariables,
        storage_phase_override: str | None = None,
    ):
        self.mongo_repo = mongo_repository
        self.postgres_repo = postgres_repository
        self.phase: TaskMessageStoragePhase = (
            storage_phase_override  # type: ignore
            if storage_phase_override
            else environment_variables.TASK_MESSAGE_STORAGE_PHASE
        )

    def _to_mongo_filters(
        self,
        filters: list[TaskMessageEntityFilter] | None,
    ) -> dict[str, Any] | None:
        """Convert entity filters to MongoDB query format."""
        if not filters:
            return None
        return _convert_filters_to_mongodb_query(filters)

    async def create(self, item: TaskMessageEntity) -> TaskMessageEntity:
        """Create message in appropriate storage(s) based on phase."""
        if self.phase == "mongodb":
            return await self.mongo_repo.create(item)

        if self.phase == "postgres":
            return await self.postgres_repo.create(item)

        # dual_write or dual_read: write to both
        mongo_result = await self.mongo_repo.create(item)
        try:
            postgres_item = TaskMessageEntity(
                id=mongo_result.id,
                task_id=mongo_result.task_id,
                content=mongo_result.content,
                streaming_status=mongo_result.streaming_status,
                created_at=mongo_result.created_at,
                updated_at=mongo_result.updated_at,
            )
            await self.postgres_repo.create(postgres_item)
        except Exception as e:
            logger.error(
                f"PostgreSQL write failed during dual-write create: {e}",
                extra={"task_id": item.task_id},
            )

        return mongo_result

    async def batch_create(
        self,
        items: List[TaskMessageEntity],  # noqa: UP006
    ) -> List[TaskMessageEntity]:  # noqa: UP006
        """Batch create messages."""
        if self.phase == "mongodb":
            return await self.mongo_repo.batch_create(items)

        if self.phase == "postgres":
            return await self.postgres_repo.batch_create(items)

        # dual_write or dual_read
        mongo_results = await self.mongo_repo.batch_create(items)
        try:
            postgres_items = [
                TaskMessageEntity(
                    id=result.id,
                    task_id=result.task_id,
                    content=result.content,
                    streaming_status=result.streaming_status,
                    created_at=result.created_at,
                    updated_at=result.updated_at,
                )
                for result in mongo_results
            ]
            await self.postgres_repo.batch_create(postgres_items)
        except Exception as e:
            logger.error(f"PostgreSQL batch_create failed during dual-write: {e}")

        return mongo_results

    async def get(
        self,
        id: str | None = None,
        name: str | None = None,
    ) -> TaskMessageEntity | None:
        """Get message from appropriate storage based on phase."""
        if self.phase in ("mongodb", "dual_write"):
            return await self.mongo_repo.get(id=id, name=name)

        if self.phase == "postgres":
            return await self.postgres_repo.get(id=id, name=name)

        # dual_read: read from both and compare
        mongo_result = await self._safe_mongo_get(id=id, name=name)
        postgres_result = await self._safe_postgres_get(id=id, name=name)

        self._log_discrepancy("get", mongo_result, postgres_result, {"id": id})
        return mongo_result

    async def update(self, item: TaskMessageEntity) -> TaskMessageEntity:
        """Update message in appropriate storage(s)."""
        if self.phase == "mongodb":
            return await self.mongo_repo.update(item)

        if self.phase == "postgres":
            return await self.postgres_repo.update(item)

        # dual_write or dual_read
        mongo_result = await self.mongo_repo.update(item)
        try:
            await self.postgres_repo.update(item)
        except Exception as e:
            logger.error(
                f"PostgreSQL update failed during dual-write: {e}",
                extra={"id": item.id},
            )

        return mongo_result

    async def batch_update(
        self,
        items: List[TaskMessageEntity],  # noqa: UP006
    ) -> List[TaskMessageEntity]:  # noqa: UP006
        """Batch update messages."""
        if self.phase == "mongodb":
            return await self.mongo_repo.batch_update(items)

        if self.phase == "postgres":
            return await self.postgres_repo.batch_update(items)

        # dual_write or dual_read
        mongo_results = await self.mongo_repo.batch_update(items)
        try:
            await self.postgres_repo.batch_update(items)
        except Exception as e:
            logger.error(f"PostgreSQL batch_update failed during dual-write: {e}")

        return mongo_results

    async def delete(self, id: str | None = None, name: str | None = None) -> None:
        """Delete message from appropriate storage(s)."""
        if self.phase == "mongodb":
            return await self.mongo_repo.delete(id=id, name=name)

        if self.phase == "postgres":
            return await self.postgres_repo.delete(id=id, name=name)

        # dual_write or dual_read
        await self.mongo_repo.delete(id=id, name=name)
        try:
            await self.postgres_repo.delete(id=id, name=name)
        except Exception as e:
            logger.error(
                f"PostgreSQL delete failed during dual-write: {e}",
                extra={"message_id": id},
            )

    async def batch_delete(
        self,
        ids: list[str] | None = None,
        names: list[str] | None = None,
    ) -> None:
        """Batch delete messages."""
        if self.phase == "mongodb":
            return await self.mongo_repo.batch_delete(ids=ids, names=names)

        if self.phase == "postgres":
            return await self.postgres_repo.batch_delete(ids=ids, names=names)

        # dual_write or dual_read
        await self.mongo_repo.batch_delete(ids=ids, names=names)
        try:
            await self.postgres_repo.batch_delete(ids=ids, names=names)
        except Exception as e:
            logger.error(f"PostgreSQL batch_delete failed during dual-write: {e}")

    async def delete_by_field(self, field_name: str, field_value: Any) -> int:
        """Delete all messages matching a field value."""
        if self.phase == "mongodb":
            return await self.mongo_repo.delete_by_field(field_name, field_value)

        if self.phase == "postgres":
            return await self.postgres_repo.delete_by_field(field_name, field_value)

        # dual_write or dual_read
        count = await self.mongo_repo.delete_by_field(field_name, field_value)
        try:
            await self.postgres_repo.delete_by_field(field_name, field_value)
        except Exception as e:
            logger.error(
                f"PostgreSQL delete_by_field failed during dual-write: {e}",
                extra={"field_name": field_name, "field_value": field_value},
            )
        return count

    async def find_by_field(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        page_number: int | None = None,
        sort_by: dict[str, int] | None = None,
        filters: list[TaskMessageEntityFilter] | None = None,
    ) -> list[TaskMessageEntity]:
        """Find messages with offset pagination."""
        if self.phase in ("mongodb", "dual_write"):
            return await self.mongo_repo.find_by_field(
                field_name=field_name,
                field_value=field_value,
                limit=limit,
                page_number=page_number,
                sort_by=sort_by,
                filters=self._to_mongo_filters(filters),
            )

        if self.phase == "postgres":
            return await self.postgres_repo.find_by_field(
                field_name=field_name,
                field_value=field_value,
                limit=limit,
                page_number=page_number,
                sort_by=sort_by,
                filters=filters,
            )

        # dual_read: compare counts
        mongo_results = await self.mongo_repo.find_by_field(
            field_name=field_name,
            field_value=field_value,
            limit=limit,
            page_number=page_number,
            sort_by=sort_by,
            filters=self._to_mongo_filters(filters),
        )
        postgres_results = await self.postgres_repo.find_by_field(
            field_name=field_name,
            field_value=field_value,
            limit=limit,
            page_number=page_number,
            sort_by=sort_by,
            filters=filters,
        )

        if len(mongo_results) != len(postgres_results):
            statsd.increment(
                METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
                tags=["operation:find_by_field"],
            )
            statsd.gauge(
                "task_message.dual_read.list_count_diff",
                abs(len(mongo_results) - len(postgres_results)),
                tags=["operation:find_by_field"],
            )
            logger.warning(
                f"find_by_field count discrepancy: MongoDB={len(mongo_results)}, "
                f"PostgreSQL={len(postgres_results)}",
                extra={
                    "field_name": field_name,
                    "field_value": field_value,
                    "limit": limit,
                },
            )

        return mongo_results

    async def find_by_field_with_cursor(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        sort_by: dict[str, int] | None = None,
        before_id: str | None = None,
        after_id: str | None = None,
        filters: list[TaskMessageEntityFilter] | None = None,
    ) -> list[TaskMessageEntity]:
        """Find messages with cursor-based pagination."""
        if self.phase in ("mongodb", "dual_write"):
            return await self.mongo_repo.find_by_field_with_cursor(
                field_name=field_name,
                field_value=field_value,
                limit=limit,
                sort_by=sort_by,
                before_id=before_id,
                after_id=after_id,
                filters=self._to_mongo_filters(filters),
            )

        if self.phase == "postgres":
            return await self.postgres_repo.find_by_field_with_cursor(
                field_name=field_name,
                field_value=field_value,
                limit=limit,
                sort_by=sort_by,
                before_id=before_id,
                after_id=after_id,
                filters=filters,
            )

        # dual_read
        mongo_results = await self.mongo_repo.find_by_field_with_cursor(
            field_name=field_name,
            field_value=field_value,
            limit=limit,
            sort_by=sort_by,
            before_id=before_id,
            after_id=after_id,
            filters=self._to_mongo_filters(filters),
        )
        postgres_results = await self.postgres_repo.find_by_field_with_cursor(
            field_name=field_name,
            field_value=field_value,
            limit=limit,
            sort_by=sort_by,
            before_id=before_id,
            after_id=after_id,
            filters=filters,
        )

        if len(mongo_results) != len(postgres_results):
            statsd.increment(
                METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
                tags=["operation:find_by_field_with_cursor"],
            )
            logger.warning(
                f"find_by_field_with_cursor count discrepancy: MongoDB={len(mongo_results)}, "
                f"PostgreSQL={len(postgres_results)}",
            )

        return mongo_results

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[TaskMessageEntity]:
        """List messages from appropriate storage."""
        if self.phase in ("mongodb", "dual_write"):
            return await self.mongo_repo.list(
                filters=filters,
                limit=limit,
                page_number=page_number,
                order_by=order_by,
                order_direction=order_direction,
            )

        if self.phase == "postgres":
            return await self.postgres_repo.list(
                filters=filters,
                limit=limit,
                page_number=page_number,
                order_by=order_by,
                order_direction=order_direction,
            )

        # dual_read: compare counts
        mongo_results = await self.mongo_repo.list(
            filters=filters,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )
        postgres_results = await self.postgres_repo.list(
            filters=filters,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )

        if len(mongo_results) != len(postgres_results):
            statsd.increment(
                METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
                tags=["operation:list"],
            )
            logger.warning(
                f"List count discrepancy: MongoDB={len(mongo_results)}, "
                f"PostgreSQL={len(postgres_results)}",
            )

        return mongo_results

    async def _safe_mongo_get(
        self,
        id: str | None = None,
        name: str | None = None,
    ) -> TaskMessageEntity | None:
        """Safely get from MongoDB, returning None on error."""
        try:
            return await self.mongo_repo.get(id=id, name=name)
        except Exception:
            return None

    async def _safe_postgres_get(
        self,
        id: str | None = None,
        name: str | None = None,
    ) -> TaskMessageEntity | None:
        """Safely get from PostgreSQL, returning None on error."""
        try:
            return await self.postgres_repo.get(id=id, name=name)
        except Exception:
            return None

    def _log_discrepancy(
        self,
        operation: str,
        mongo_result: TaskMessageEntity | None,
        postgres_result: TaskMessageEntity | None,
        context: dict[str, Any],
    ) -> None:
        """Log discrepancies between MongoDB and PostgreSQL results and emit metrics."""
        tags = [f"operation:{operation}"]

        if mongo_result is None and postgres_result is None:
            return

        if mongo_result is None and postgres_result is not None:
            statsd.increment(METRIC_DUAL_READ_MISSING_MONGODB, tags=tags)
            logger.warning(
                f"Discrepancy in {operation}: MongoDB=None, PostgreSQL=exists",
                extra=context,
            )
            return

        if mongo_result is not None and postgres_result is None:
            statsd.increment(METRIC_DUAL_READ_MISSING_POSTGRES, tags=tags)
            logger.warning(
                f"Discrepancy in {operation}: MongoDB=exists, PostgreSQL=None",
                extra=context,
            )
            return

        # Both exist - compare content
        mongo_content = (
            mongo_result.content.model_dump() if mongo_result.content else None
        )
        postgres_content = (
            postgres_result.content.model_dump() if postgres_result.content else None
        )
        if mongo_content != postgres_content:
            statsd.increment(METRIC_DUAL_READ_CONTENT_MISMATCH, tags=tags)
            logger.warning(
                f"Content discrepancy in {operation} for id={mongo_result.id}",
                extra=context,
            )
            return

        statsd.increment(METRIC_DUAL_READ_MATCH, tags=tags)


def get_task_message_dual_repository(
    mongo_repository: DTaskMessageRepository,
    postgres_repository: DTaskMessagePostgresRepository,
    environment_variables: DEnvironmentVariables,
    message_storage_backend: str | None = Query(
        None,
        description="Override storage backend: mongodb, dual_write, dual_read, or postgres",
        pattern="^(mongodb|dual_write|dual_read|postgres)$",
    ),
) -> TaskMessageDualRepository:
    """Factory function that creates TaskMessageDualRepository with optional storage backend override."""
    return TaskMessageDualRepository(
        mongo_repository=mongo_repository,
        postgres_repository=postgres_repository,
        environment_variables=environment_variables,
        storage_phase_override=message_storage_backend,
    )


DTaskMessageDualRepository = Annotated[
    TaskMessageDualRepository, Depends(get_task_message_dual_repository)
]
