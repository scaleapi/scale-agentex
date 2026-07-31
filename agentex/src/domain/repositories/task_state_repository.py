import builtins
from typing import Annotated, Any, Protocol

import pymongo
from fastapi import Depends
from src.adapters.crud_store.adapter_mongodb import MongoDBCRUDRepository
from src.config.dependencies import DMongoDBDatabase, GlobalDependencies
from src.config.environment_variables import EnvironmentVariables, StoragePhase
from src.domain.entities.states import StateEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskStateRepositoryProtocol(Protocol):
    """Contract every task-state storage backend must satisfy.

    Covers everything callers actually invoke through the DTaskStateRepository
    seam: the states use case and authorization shortcuts (create / get /
    update / delete / list), the retention service (find_by_field /
    delete_by_field / batch_create), and get_by_task_and_agent.

    Behavioral requirements beyond the signatures: `.id` is presented as a
    string; `create` honors caller-supplied created_at/updated_at and only
    falls back to server time when absent; missing rows raise ItemDoesNotExist
    and duplicates raise DuplicateItemError; and `list` accepts the
    Mongo-shaped filter dict the states use case builds (plain equality plus
    `{"$in": [...]}` for the authorized-task allow-list).
    """

    async def create(self, item: StateEntity) -> StateEntity: ...

    async def batch_create(
        self, items: builtins.list[StateEntity]
    ) -> builtins.list[StateEntity]: ...

    async def get(
        self, id: str | None = None, name: str | None = None
    ) -> StateEntity | None: ...

    async def update(self, item: StateEntity) -> StateEntity: ...

    async def delete(self, id: str | None = None, name: str | None = None) -> None: ...

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> builtins.list[StateEntity]: ...

    async def find_by_field(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        page_number: int | None = None,
        sort_by: dict[str, int] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> builtins.list[StateEntity]: ...

    async def delete_by_field(self, field_name: str, field_value: Any) -> int: ...

    async def get_by_task_and_agent(
        self, task_id: str, agent_id: str
    ) -> StateEntity | None: ...


class TaskStateRepository(MongoDBCRUDRepository[StateEntity]):
    """Repository for managing task states in MongoDB."""

    COLLECTION_NAME = "task_states"

    # Define indexes as static configuration
    # These will be created once at startup, not per request
    INDEXES = [
        {
            "keys": [("task_id", pymongo.ASCENDING), ("agent_id", pymongo.ASCENDING)],
            "name": "task_agent_compound_idx",
            "description": "Compound index for get_by_task_and_agent queries",
        },
        {
            "keys": [("task_id", pymongo.ASCENDING)],
            "name": "task_id_idx",
            "description": "Single index for task_id queries",
        },
        {
            "keys": [("agent_id", pymongo.ASCENDING)],
            "name": "agent_id_idx",
            "description": "Single index for agent_id queries",
        },
    ]

    def __init__(self, db: DMongoDBDatabase):
        super().__init__(
            db=db, collection_name=self.COLLECTION_NAME, model_class=StateEntity
        )

    async def get_by_task_and_agent(
        self, task_id: str, agent_id: str
    ) -> StateEntity | None:
        doc = await self.collection.find_one({"task_id": task_id, "agent_id": agent_id})
        return self._deserialize(doc) if doc else None


def get_task_state_repository() -> TaskStateRepositoryProtocol:
    """Select the task-state repository for the configured storage phase.

    This is the single construction point for task-state repositories: the
    FastAPI seam below resolves through it, and so must every site that builds
    the repository by hand outside Depends (the Temporal factories), so that a
    phase switch applies to request handlers and workers alike.

    Each branch constructs its repository lazily — the Postgres phase must
    never touch a Mongo handle, which is what allows the MongoDB connection to
    be absent entirely once no store needs it.
    """
    phase = EnvironmentVariables.refresh().TASK_STATE_STORAGE_PHASE
    if phase == StoragePhase.MONGODB:
        return TaskStateRepository(GlobalDependencies().mongodb_database)
    # Unreachable through env config (refresh() rejects unimplemented phases
    # at startup); defense in depth for configs constructed another way.
    raise NotImplementedError(
        f"TASK_STATE_STORAGE_PHASE={phase.value!r} is not implemented yet; "
        "only 'mongodb' is currently supported."
    )


DTaskStateRepository = Annotated[
    TaskStateRepositoryProtocol, Depends(get_task_state_repository)
]
