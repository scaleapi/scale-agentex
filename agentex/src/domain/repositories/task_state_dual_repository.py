# Note: List is used instead of list because the class has a method named 'list'
# which shadows the builtin in the class body for type annotations
from typing import Annotated, Any, List, Literal  # noqa: UP035

from datadog import statsd
from fastapi import Depends, Query
from src.config.dependencies import DEnvironmentVariables
from src.domain.entities.states import StateEntity
from src.domain.repositories.task_state_postgres_repository import (
    DTaskStatePostgresRepository,
)
from src.domain.repositories.task_state_repository import (
    DTaskStateRepository,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

TaskStateStoragePhase = Literal["mongodb", "dual_write", "dual_read", "postgres"]

# Metric names for dual-read verification
METRIC_DUAL_READ_MATCH = "task_state.dual_read.match"
METRIC_DUAL_READ_MISSING_POSTGRES = "task_state.dual_read.mismatch.missing_postgres"
METRIC_DUAL_READ_MISSING_MONGODB = "task_state.dual_read.mismatch.missing_mongodb"
METRIC_DUAL_READ_STATE_MISMATCH = "task_state.dual_read.mismatch.state_content"
METRIC_DUAL_READ_LIST_COUNT_MISMATCH = "task_state.dual_read.list_count_mismatch"


class TaskStateDualRepository:
    """
    Dual-write repository that manages task state storage across MongoDB and PostgreSQL.

    Phases:
    - mongodb: Read/write only MongoDB (legacy behavior)
    - dual_write: Write to both, read from MongoDB
    - dual_read: Write to both, read from both (verify consistency)
    - postgres: Read/write only PostgreSQL (target state)

    This wrapper enables a safe migration from MongoDB to PostgreSQL by:
    1. First enabling dual-write to populate PostgreSQL
    2. Then enabling dual-read to verify data consistency
    3. Finally switching to PostgreSQL only
    """

    def __init__(
        self,
        mongo_repository: DTaskStateRepository,
        postgres_repository: DTaskStatePostgresRepository,
        environment_variables: DEnvironmentVariables,
        storage_phase_override: str | None = None,
    ):
        self.mongo_repo = mongo_repository
        self.postgres_repo = postgres_repository
        # Use override if provided, otherwise fall back to env var
        self.phase: TaskStateStoragePhase = (
            storage_phase_override  # type: ignore
            if storage_phase_override
            else environment_variables.TASK_STATE_STORAGE_PHASE
        )

    async def create(self, item: StateEntity) -> StateEntity:
        """Create state in appropriate storage(s) based on phase."""
        if self.phase == "mongodb":
            return await self.mongo_repo.create(item)

        if self.phase == "postgres":
            return await self.postgres_repo.create(item)

        # dual_write or dual_read: write to both
        mongo_result = await self.mongo_repo.create(item)
        try:
            # Create a copy of the item with the MongoDB-generated ID for PostgreSQL
            postgres_item = StateEntity(
                id=mongo_result.id,
                task_id=mongo_result.task_id,
                agent_id=mongo_result.agent_id,
                state=mongo_result.state,
                created_at=mongo_result.created_at,
                updated_at=mongo_result.updated_at,
            )
            await self.postgres_repo.create(postgres_item)
        except Exception as e:
            logger.error(
                f"PostgreSQL write failed during dual-write create: {e}",
                extra={"task_id": item.task_id, "agent_id": item.agent_id},
            )
            # Continue with MongoDB result - postgres is secondary during migration

        return mongo_result

    async def get(
        self, id: str | None = None, name: str | None = None
    ) -> StateEntity | None:
        """Get state from appropriate storage based on phase."""
        if self.phase in ("mongodb", "dual_write"):
            return await self.mongo_repo.get(id=id, name=name)

        if self.phase == "postgres":
            return await self.postgres_repo.get(id=id, name=name)

        # dual_read: read from both and compare
        mongo_result = await self._safe_mongo_get(id=id, name=name)
        postgres_result = await self._safe_postgres_get(id=id, name=name)

        self._log_discrepancy("get", mongo_result, postgres_result, {"id": id})
        return mongo_result  # Still return MongoDB result as primary

    async def get_by_task_and_agent(
        self, task_id: str, agent_id: str
    ) -> StateEntity | None:
        """Get state by task and agent combination."""
        if self.phase in ("mongodb", "dual_write"):
            return await self.mongo_repo.get_by_task_and_agent(task_id, agent_id)

        if self.phase == "postgres":
            return await self.postgres_repo.get_by_task_and_agent(task_id, agent_id)

        # dual_read
        mongo_result = await self.mongo_repo.get_by_task_and_agent(task_id, agent_id)
        postgres_result = await self.postgres_repo.get_by_task_and_agent(
            task_id, agent_id
        )

        self._log_discrepancy(
            "get_by_task_and_agent",
            mongo_result,
            postgres_result,
            {"task_id": task_id, "agent_id": agent_id},
        )
        return mongo_result

    async def update(self, item: StateEntity) -> StateEntity:
        """Update state in appropriate storage(s)."""
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

    async def delete(self, id: str | None = None, name: str | None = None) -> None:
        """Delete state from appropriate storage(s)."""
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
                extra={"state_id": id, "state_name": name},
            )

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[StateEntity]:
        """List states from appropriate storage."""
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
            statsd.gauge(
                "task_state.dual_read.list_count_diff",
                abs(len(mongo_results) - len(postgres_results)),
                tags=["operation:list"],
            )
            logger.warning(
                f"List count discrepancy: MongoDB={len(mongo_results)}, "
                f"PostgreSQL={len(postgres_results)}",
                extra={"filters": filters, "limit": limit, "page_number": page_number},
            )

        return mongo_results

    async def batch_create(self, items: List[StateEntity]) -> List[StateEntity]:  # noqa: UP006
        """Batch create states."""
        if self.phase == "mongodb":
            return await self.mongo_repo.batch_create(items)

        if self.phase == "postgres":
            return await self.postgres_repo.batch_create(items)

        # dual_write or dual_read
        mongo_results = await self.mongo_repo.batch_create(items)
        try:
            # Create copies with MongoDB-generated IDs for PostgreSQL
            postgres_items = [
                StateEntity(
                    id=result.id,
                    task_id=result.task_id,
                    agent_id=result.agent_id,
                    state=result.state,
                    created_at=result.created_at,
                    updated_at=result.updated_at,
                )
                for result in mongo_results
            ]
            await self.postgres_repo.batch_create(postgres_items)
        except Exception as e:
            logger.error(f"PostgreSQL batch_create failed during dual-write: {e}")

        return mongo_results

    async def _safe_mongo_get(
        self, id: str | None = None, name: str | None = None
    ) -> StateEntity | None:
        """Safely get from MongoDB, returning None on ItemDoesNotExist."""
        try:
            return await self.mongo_repo.get(id=id, name=name)
        except Exception:
            return None

    async def _safe_postgres_get(
        self, id: str | None = None, name: str | None = None
    ) -> StateEntity | None:
        """Safely get from PostgreSQL, returning None on ItemDoesNotExist."""
        try:
            return await self.postgres_repo.get(id=id, name=name)
        except Exception:
            return None

    def _log_discrepancy(
        self,
        operation: str,
        mongo_result: StateEntity | None,
        postgres_result: StateEntity | None,
        context: dict[str, Any],
    ) -> None:
        """Log any discrepancies between MongoDB and PostgreSQL results and emit metrics."""
        tags = [f"operation:{operation}"]

        # Both None - nothing to compare (no metric needed)
        if mongo_result is None and postgres_result is None:
            return

        # Check for missing data scenarios
        if mongo_result is None and postgres_result is not None:
            # Data exists in PostgreSQL but not MongoDB (unexpected)
            statsd.increment(METRIC_DUAL_READ_MISSING_MONGODB, tags=tags)
            logger.warning(
                f"Discrepancy in {operation}: MongoDB=None, PostgreSQL=exists",
                extra=context,
            )
            return

        if mongo_result is not None and postgres_result is None:
            # Data exists in MongoDB but not PostgreSQL (migration gap)
            statsd.increment(METRIC_DUAL_READ_MISSING_POSTGRES, tags=tags)
            logger.warning(
                f"Discrepancy in {operation}: MongoDB=exists, PostgreSQL=None",
                extra=context,
            )
            return

        # Both exist - compare state content
        if mongo_result.state != postgres_result.state:
            statsd.increment(METRIC_DUAL_READ_STATE_MISMATCH, tags=tags)
            logger.warning(
                f"State content discrepancy in {operation} for id={mongo_result.id}",
                extra={
                    **context,
                    "mongo_state_keys": [*mongo_result.state.keys()]
                    if mongo_result.state
                    else [],
                    "postgres_state_keys": [*postgres_result.state.keys()]
                    if postgres_result.state
                    else [],
                },
            )
            return

        # Data matches - emit success metric
        statsd.increment(METRIC_DUAL_READ_MATCH, tags=tags)


def get_task_state_dual_repository(
    mongo_repository: DTaskStateRepository,
    postgres_repository: DTaskStatePostgresRepository,
    environment_variables: DEnvironmentVariables,
    storage_backend: str | None = Query(
        None,
        description="Override storage backend: mongodb, dual_write, dual_read, or postgres",
        pattern="^(mongodb|dual_write|dual_read|postgres)$",
    ),
) -> TaskStateDualRepository:
    """Factory function that creates TaskStateDualRepository with optional storage backend override."""
    return TaskStateDualRepository(
        mongo_repository=mongo_repository,
        postgres_repository=postgres_repository,
        environment_variables=environment_variables,
        storage_phase_override=storage_backend,
    )


DTaskStateDualRepository = Annotated[
    TaskStateDualRepository, Depends(get_task_state_dual_repository)
]
