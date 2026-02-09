from typing import Annotated

import pymongo
from fastapi import Depends
from src.adapters.crud_store.adapter_mongodb import MongoDBCRUDRepository
from src.config.dependencies import DMongoDBDatabase
from src.domain.entities.task_messages import TaskMessageEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskMessageRepository(MongoDBCRUDRepository[TaskMessageEntity]):
    """Repository for managing task messages in MongoDB."""

    COLLECTION_NAME = "messages"

    # Define indexes as static configuration
    # These will be created once at startup, not per request
    INDEXES = [
        {
            "keys": [
                ("task_id", pymongo.ASCENDING),
                ("created_at", pymongo.DESCENDING),
            ],
            "name": "task_id_created_at_idx",
            "description": "Compound index for querying messages by task_id and sorting by created_at",
        },
        {
            "keys": [("task_id", pymongo.ASCENDING)],
            "name": "task_id_idx",
            "description": "Single index for task_id queries and delete operations",
        },
        {
            "keys": [
                ("task_id", pymongo.ASCENDING),
                ("streaming_status", pymongo.ASCENDING),
            ],
            "name": "task_id_streaming_status_idx",
            "description": "Index for streaming status queries during streaming operations",
        },
        {
            "keys": [
                ("task_id", pymongo.ASCENDING),
                ("content.type", pymongo.ASCENDING),
                ("created_at", pymongo.DESCENDING),
            ],
            "name": "task_id_content_type_created_at_idx",
            "description": "Compound index for filtering messages by task_id, content type, and sorting by created_at",
        },
    ]

    def __init__(self, db: DMongoDBDatabase):
        super().__init__(
            db=db, collection_name=self.COLLECTION_NAME, model_class=TaskMessageEntity
        )


DTaskMessageRepository = Annotated[
    TaskMessageRepository, Depends(TaskMessageRepository)
]
