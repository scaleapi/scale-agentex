"""
MongoDB index management module.

This module handles the creation of MongoDB indexes at application startup.
Indexes are defined in repository classes and created once during initialization,
not on every request.
"""

from typing import Any

from pymongo.database import Database as MongoDBDatabase
from pymongo.errors import OperationFailure

from src.utils.logging import make_logger

logger = make_logger(__name__)


def ensure_mongodb_indexes(mongodb_database: MongoDBDatabase) -> None:
    """
    Create all MongoDB indexes defined in repository classes.

    This function is called once during application startup to create all necessary
    indexes. It discovers repository classes that define indexes and creates them
    on the appropriate collections.

    Args:
        mongodb_database: The MongoDB database instance
    """
    # Import repository classes here to avoid circular imports
    from src.domain.repositories.task_message_repository import TaskMessageRepository
    from src.domain.repositories.task_state_repository import TaskStateRepository

    # List of repository classes that may have index definitions
    repository_classes = [
        TaskMessageRepository,
        TaskStateRepository,
    ]

    logger.info("Starting MongoDB index creation...")

    for repo_class in repository_classes:
        # Check if the repository class has index definitions
        if not hasattr(repo_class, "INDEXES") or not hasattr(
            repo_class, "COLLECTION_NAME"
        ):
            continue

        collection_name = repo_class.COLLECTION_NAME
        indexes = repo_class.INDEXES

        if not indexes:
            continue

        logger.info(f"Creating indexes for collection '{collection_name}'...")
        collection = mongodb_database[collection_name]

        for index_spec in indexes:
            try:
                # Extract index configuration
                keys = index_spec.get("keys", [])
                name = index_spec.get("name")
                description = index_spec.get("description", "")

                # Additional index options can be added here
                index_kwargs = {"name": name} if name else {}

                # Check if any other options are specified
                for key in [
                    "unique",
                    "sparse",
                    "expireAfterSeconds",
                    "partialFilterExpression",
                ]:
                    if key in index_spec:
                        index_kwargs[key] = index_spec[key]

                # Create the index
                result = collection.create_index(keys, **index_kwargs)

                if description:
                    logger.info(f"  ✓ Created index '{name or result}': {description}")
                else:
                    logger.info(f"  ✓ Created index '{name or result}'")

            except OperationFailure as e:
                # Index might already exist with different options
                if "already exists with different options" in str(e):
                    logger.warning(
                        f"  ⚠ Index '{index_spec.get('name', 'unnamed')}' already exists "
                        f"with different options. You may need to drop and recreate it."
                    )
                else:
                    logger.error(f"  ✗ Failed to create index: {e}")
            except Exception as e:
                logger.error(
                    f"  ✗ Unexpected error creating index '{index_spec.get('name', 'unnamed')}': {e}"
                )

    logger.info("MongoDB index creation completed.")


def drop_all_indexes(mongodb_database: MongoDBDatabase) -> None:
    """
    Drop all non-_id indexes from MongoDB collections.

    WARNING: This function drops all indexes except the default _id index.
    Use with caution, typically only in development or migration scenarios.

    Args:
        mongodb_database: The MongoDB database instance
    """
    from src.domain.repositories.task_message_repository import TaskMessageRepository
    from src.domain.repositories.task_state_repository import TaskStateRepository

    repository_classes = [
        TaskMessageRepository,
        TaskStateRepository,
    ]

    logger.warning("Dropping all MongoDB indexes (except _id)...")

    for repo_class in repository_classes:
        if not hasattr(repo_class, "COLLECTION_NAME"):
            continue

        collection_name = repo_class.COLLECTION_NAME
        collection = mongodb_database[collection_name]

        try:
            # Drop all indexes except _id
            collection.drop_indexes()
            logger.info(f"  ✓ Dropped all indexes from collection '{collection_name}'")
        except Exception as e:
            logger.error(f"  ✗ Failed to drop indexes from '{collection_name}': {e}")

    logger.warning("Index dropping completed.")


def get_index_stats(mongodb_database: MongoDBDatabase) -> dict[str, Any]:
    """
    Get statistics about indexes for all collections.

    Args:
        mongodb_database: The MongoDB database instance

    Returns:
        Dictionary containing index statistics for each collection
    """
    from src.domain.repositories.task_message_repository import TaskMessageRepository
    from src.domain.repositories.task_state_repository import TaskStateRepository

    repository_classes = [
        TaskMessageRepository,
        TaskStateRepository,
    ]

    stats = {}

    for repo_class in repository_classes:
        if not hasattr(repo_class, "COLLECTION_NAME"):
            continue

        collection_name = repo_class.COLLECTION_NAME
        collection = mongodb_database[collection_name]

        try:
            indexes = list(collection.list_indexes())
            stats[collection_name] = {
                "count": len(indexes),
                "indexes": [
                    {
                        "name": idx.get("name"),
                        "keys": idx.get("key"),
                        "unique": idx.get("unique", False),
                        "sparse": idx.get("sparse", False),
                    }
                    for idx in indexes
                ],
            }
        except Exception as e:
            logger.error(f"Failed to get index stats for '{collection_name}': {e}")
            stats[collection_name] = {"error": str(e)}

    return stats
