from typing import Annotated

import pymongo
from fastapi import Depends
from src.adapters.crud_store.adapter_mongodb import MongoDBCRUDRepository
from src.config.dependencies import DMongoDBDatabase
from src.domain.entities.states import StateEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskStateRepository(MongoDBCRUDRepository[StateEntity]):
    """Repository for managing task states in MongoDB."""

    COLLECTION_NAME = "task_states"

    # Define indexes as static configuration
    # These will be created once at startup, not per request
    INDEXES = [
        {
            "keys": [("task_id", pymongo.ASCENDING), ("agent_id", pymongo.ASCENDING)],
            "name": "task_agent_compound_idx",
            "unique": True,
            "description": "Unique compound index for get_by_task_and_agent queries",
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
        doc = self.collection.find_one({"task_id": task_id, "agent_id": agent_id})
        return self._deserialize(doc) if doc else None


DTaskStateRepository = Annotated[TaskStateRepository, Depends(TaskStateRepository)]
