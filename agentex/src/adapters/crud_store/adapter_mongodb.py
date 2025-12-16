import asyncio
import builtins
import random
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Generic, TypeVar

import pymongo
from bson import ObjectId
from pymongo.collection import Collection

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.adapters.crud_store.port import CRUDRepository
from src.config.dependencies import DMongoDBDatabase
from src.domain.exceptions import ClientError, ServiceError
from src.utils.logging import make_logger

logger = make_logger(__name__)

T = TypeVar("T")

DEFAULT_PAGE_LIMIT = 50


def retry_write_operation(max_retries: int = 3, base_delay: float = 0.1):
    """
    Decorator to retry MongoDB write operations with exponential backoff.
    This provides application-level retry logic for high-scale environments.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds between retries
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (
                    pymongo.errors.AutoReconnect,
                    pymongo.errors.NetworkTimeout,
                    pymongo.errors.ServerSelectionTimeoutError,
                ) as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Exponential backoff with jitter
                        delay = base_delay * (2**attempt) + random.uniform(0, 0.1)
                        logger.warning(
                            f"Write operation failed on attempt {attempt + 1}, retrying in {delay:.2f}s: {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Write operation failed after {max_retries + 1} attempts: {e}"
                        )
                except Exception as e:
                    # Don't retry non-transient errors
                    raise e

            # If we get here, all retries failed
            raise ServiceError(
                message=f"Write operation failed after {max_retries + 1} attempts",
                detail=str(last_exception),
            ) from last_exception

        return wrapper

    return decorator


class MongoDBCRUDRepository(CRUDRepository[T], Generic[T]):
    """
    A generic MongoDB repository implementation for CRUD operations.
    This repository supports retrieval by ID or name and works with arbitrary models.
    Note: Indexes are assumed to be created externally.

    The repository handles conversion between model's .id field and MongoDB's _id field.
    Callers should always work with .id fields, and the conversion to/from _id is handled internally.

    Automatic timestamp handling:
    - created_at: Automatically set when a document is created
    - updated_at: Automatically updated when a document is modified

    AWS DocumentDB Compatibility:
    - Retryable writes are disabled in the connection (AWS DocumentDB doesn't support them)
    - Application-level retry logic is implemented for transient failures
    - Write operations are decorated with @retry_write_operation for resilience
    """

    def __init__(
        self,
        db: DMongoDBDatabase,
        collection_name: str,
        model_class: type[T],
    ):
        self.db = db
        self.collection: Collection = db[collection_name]
        self.model_class = model_class

        # MongoDB already enforces uniqueness on _id
        # No need to create additional indexes for id

        # Note: Specific indexes should be created by individual repository classes
        # that extend this base class, as they know their query patterns best.
        # Generic indexes on created_at/updated_at are often not useful and can
        # slow down writes without providing query benefits.

    def _convert_id(self, id_value: str | ObjectId) -> ObjectId | Any:
        """Convert a string ID to ObjectId if applicable."""
        if isinstance(id_value, str):
            try:
                return ObjectId(id_value)
            except Exception as e:
                logger.error(f"Invalid ObjectId '{id_value}': {e}")
                return id_value
        return id_value

    def _serialize(self, obj: T) -> dict[str, Any]:
        """
        Convert a model object to a dictionary for MongoDB storage.
        Maps .id to _id field for MongoDB.
        """
        if isinstance(obj, dict):
            data = obj.copy()
        elif hasattr(obj, "dict"):
            data = obj.dict()
        elif hasattr(obj, "model_dump"):
            data = obj.model_dump()
        elif hasattr(obj, "to_dict"):
            data = obj.to_dict()
        elif hasattr(obj, "__dict__"):
            data = vars(obj)
        else:
            raise ValueError("Unable to serialize object of unknown type.")

        # Handle mapping between .id and _id
        # If the object has an .id attribute, map the .id value to _id field
        if "id" in data and data["id"] is not None:
            try:
                # Map model's .id to MongoDB's _id
                if isinstance(data["id"], str):
                    try:
                        data["_id"] = ObjectId(data["id"])
                    except Exception:
                        data["_id"] = data["id"]
                else:
                    data["_id"] = data["id"]

                # Delete id field to avoid duplicate fields (_id is used by MongoDB)
                del data["id"]
            except Exception as e:
                logger.error(f"Error mapping id to _id: {e}")

        # Always convert _id to ObjectId if it's a string
        if "_id" in data and isinstance(data["_id"], str):
            try:
                data["_id"] = ObjectId(data["_id"])
            except Exception:
                pass

        return data

    def _deserialize(self, data: dict[str, Any]) -> T | None:
        """
        Convert a MongoDB document to a model object.
        Maps _id to .id field for model consistency.
        """
        if not data:
            return None

        # Handle mapping between _id and .id
        if "_id" in data:
            # Always convert MongoDB's _id to string for the model's .id
            if isinstance(data["_id"], ObjectId):
                data["id"] = str(data["_id"])
            else:
                data["id"] = data["_id"]

            # Remove _id to avoid confusion with model fields
            del data["_id"]

        if hasattr(self.model_class, "parse_obj"):
            return self.model_class.parse_obj(data)
        elif hasattr(self.model_class, "model_validate"):
            return self.model_class.model_validate(data)
        elif hasattr(self.model_class, "from_dict"):
            return self.model_class.from_dict(data)
        else:
            return self.model_class(**data)

    @retry_write_operation()
    async def create(self, item: T) -> T:
        """
        Create a new document.
        Maps .id to _id and handles auto-generation of ids.
        Automatically sets created_at and updated_at timestamps.
        """
        try:
            data = self._serialize(item)

            # For MongoDB's default _id, allow it to be auto-generated if not present
            if "_id" not in data or data["_id"] is None:
                if "_id" in data:
                    del data["_id"]

            # Add timestamps
            now = datetime.now(UTC)
            data["created_at"] = now
            data["updated_at"] = now

            result = self.collection.insert_one(data)

            # Update item with generated ID (as string)
            # Set the .id field with the string representation of _id
            if hasattr(item, "id"):
                item.id = str(result.inserted_id)
                # Set timestamps on the returned object
                item.created_at = now
                item.updated_at = now
            elif isinstance(item, dict):
                item["id"] = str(result.inserted_id)
                item["created_at"] = now
                item["updated_at"] = now

            return item
        except pymongo.errors.DuplicateKeyError as e:
            raise DuplicateItemError(
                message="Item with this id already exists. IDs must be unique.",
                detail=str(e),
            ) from e
        except ClientError:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to create item in MongoDB: {e}", detail=str(e)
            ) from e

    @retry_write_operation()
    async def batch_create(self, items: list[T]) -> list[T]:
        """
        Create multiple documents.
        Maps .id to _id for each item and handles auto-generation of ids.
        Automatically sets created_at and updated_at timestamps.
        """
        if not items:
            return []
        try:
            data_list = []
            now = datetime.now(UTC)
            for item in items:
                data = self._serialize(item)

                # For MongoDB's default _id, allow it to be auto-generated if not present
                if "_id" not in data or data["_id"] is None:
                    data.pop("_id", None)

                # Add timestamps
                data["created_at"] = now
                data["updated_at"] = now

                data_list.append(data)

            result = self.collection.insert_many(data_list)

            # Update items with generated IDs (as strings)
            for idx, inserted_id in enumerate(result.inserted_ids):
                # Set the .id field with the string representation of _id
                if hasattr(items[idx], "id"):
                    items[idx].id = str(inserted_id)
                    items[idx].created_at = now
                    items[idx].updated_at = now
                elif isinstance(items[idx], dict):
                    items[idx]["id"] = str(inserted_id)
                    items[idx]["created_at"] = now
                    items[idx]["updated_at"] = now

            return items
        except pymongo.errors.DuplicateKeyError as e:
            raise DuplicateItemError(
                message="One or more items have duplicate id values. IDs must be unique.",
                detail=str(e),
            ) from e
        except ClientError:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to batch create items in MongoDB: {e}", detail=str(e)
            ) from e

    async def get(self, id: str | None = None, name: str | None = None) -> T | None:
        """
        Retrieve a document by its ID or name.
        Maps .id to _id when querying by ID and _id to .id in returned item.
        """
        if id is None and name is None:
            raise ClientError("Either id or name must be provided.")
        try:
            if id is not None:
                # Use _id for MongoDB when querying by id
                id_value = self._convert_id(id)
                query = {"_id": id_value}
            else:
                query = {"name": name}

            document = self.collection.find_one(query)
            if document is None:
                msg = (
                    f"Item with {'id' if id else 'name'} '{id or name}' does not exist."
                )
                raise ItemDoesNotExist(msg)
            return self._deserialize(document)
        except ItemDoesNotExist:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to get item from MongoDB: {e}", detail=str(e)
            ) from e

    async def get_by_field(self, field_name: str, field_value: Any) -> T | None:
        """
        Find a single document by a given field.
        Uses find_one() for better efficiency when only one document is needed.

        Args:
            field_name: The field name to search by
            field_value: The value to search for

        Returns:
            A single document matching the field criteria or None if not found

        Raises:
            ItemDoesNotExist: If no document matches the criteria
            ServiceError: If there's an error executing the query
        """
        try:
            # Map 'id' field to '_id' for MongoDB if needed
            mongo_field_name = "_id" if field_name == "id" else field_name
            mongo_field_value = field_value

            # Convert id string to ObjectId if searching by _id
            if mongo_field_name == "_id" and isinstance(mongo_field_value, str):
                try:
                    mongo_field_value = ObjectId(mongo_field_value)
                except Exception:
                    pass

            document = self.collection.find_one({mongo_field_name: mongo_field_value})
            if document is None:
                raise ItemDoesNotExist(
                    f"Item with {field_name} '{field_value}' does not exist."
                )
            return self._deserialize(document)
        except ItemDoesNotExist:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to get item by field from MongoDB: {e}", detail=str(e)
            ) from e

    async def batch_get(
        self, ids: list[str] | None = None, names: list[str] | None = None
    ) -> list[T]:
        """
        Retrieve multiple documents by their IDs or names.
        Maps .id values to _id when querying by IDs and _id to .id in returned items.
        """
        if not ids and not names:
            raise ClientError("Either ids or names must be provided.")
        try:
            query = {}
            if ids:
                # Use _id for MongoDB when querying by ids
                query["_id"] = {"$in": [self._convert_id(_id) for _id in ids]}
            elif names:
                query["name"] = {"$in": names}

            cursor = self.collection.find(query)
            results = list(cursor)
            if not results:
                key = "ids" if ids else "names"
                msg = f"No items found with {key} '{ids or names}'."
                raise ItemDoesNotExist(msg)
            return [self._deserialize(doc) for doc in results]
        except ItemDoesNotExist:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to batch get items from MongoDB: {e}", detail=str(e)
            ) from e

    @retry_write_operation()
    async def update(self, item: T) -> T:
        """
        Update an existing document.
        Maps .id to _id for querying MongoDB.
        Automatically updates the updated_at timestamp.
        """
        try:
            data = self._serialize(item)

            # Get the MongoDB _id value for querying
            id_value = data.get("_id")
            if id_value is None:
                raise ClientError("Item must have an ID for update.")

            # Prepare update data by excluding the _id field and created_at (should never be updated)
            update_data = {
                k: v for k, v in data.items() if k not in ("_id", "created_at")
            }

            # Add updated_at timestamp
            update_data["updated_at"] = datetime.now(UTC)

            result = self.collection.update_one(
                {"_id": id_value}, {"$set": update_data}
            )

            if result.matched_count == 0:
                raise ItemDoesNotExist(f"Item with id '{id_value}' does not exist.")

            updated_doc = self.collection.find_one({"_id": id_value})
            return self._deserialize(updated_doc)
        except ItemDoesNotExist:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to update item in MongoDB: {e}", detail=str(e)
            ) from e

    async def batch_update(self, items: list[T]) -> list[T]:
        """
        Update multiple documents.
        Maps .id to _id for each item when querying MongoDB.
        """
        updated_items = []
        for item in items:
            try:
                updated_item = await self.update(item)
                if updated_item:
                    updated_items.append(updated_item)
            except ItemDoesNotExist:
                continue
        return updated_items

    @retry_write_operation()
    async def delete(self, id: str | None = None, name: str | None = None) -> None:
        """
        Delete a document by its ID or name.
        Maps .id to _id when querying by ID.
        """
        if id is None and name is None:
            raise ClientError("Either id or name must be provided.")
        try:
            if id is not None:
                # Use _id for MongoDB when deleting by id
                id_value = self._convert_id(id)
                query = {"_id": id_value}
            else:
                query = {"name": name}

            result = self.collection.delete_one(query)
            if result.deleted_count == 0:
                msg = (
                    f"Item with {'id' if id else 'name'} '{id or name}' does not exist."
                )
                raise ItemDoesNotExist(msg)
        except ItemDoesNotExist:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to delete item from MongoDB: {e}", detail=str(e)
            ) from e

    @retry_write_operation()
    async def batch_delete(
        self, ids: list[str] | None = None, names: list[str] | None = None
    ) -> None:
        """
        Delete multiple documents by their IDs or names.
        Maps .id values to _id when querying by IDs.
        """
        if not ids and not names:
            raise ClientError("Either ids or names must be provided.")
        try:
            query = {}
            if ids:
                # Use _id for MongoDB when deleting by ids
                query["_id"] = {"$in": [self._convert_id(_id) for _id in ids]}
            elif names:
                query["name"] = {"$in": names}

            result = self.collection.delete_many(query)
            if result.deleted_count == 0:
                key = "ids" if ids else "names"
                msg = f"No items found with {key} '{ids or names}'."
                raise ItemDoesNotExist(msg)
        except ItemDoesNotExist:
            raise
        except Exception as e:
            raise ServiceError(
                message=f"Failed to batch delete items from MongoDB: {e}", detail=str(e)
            ) from e

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[T]:
        """
        List all documents in the collection.
        Maps _id to .id for each returned item.
        """
        limit = limit or DEFAULT_PAGE_LIMIT
        if page_number is not None and page_number < 1:
            raise ClientError("Page number must be greater than 0")
        page_number = page_number or 1
        skip = (page_number - 1) * limit
        if filters:
            cursor = self.collection.find(filters)
        else:
            cursor = self.collection.find()
        cursor = cursor.skip(skip).limit(limit)

        sort_list = []
        if order_by:
            direction = (
                pymongo.DESCENDING
                if order_direction and order_direction.lower() == "desc"
                else pymongo.ASCENDING
            )
            sort_list.append((order_by, direction))

        # Always use _id as tiebreaker
        sort_list.append(("_id", pymongo.ASCENDING))
        cursor = cursor.sort(sort_list)

        try:
            return [self._deserialize(doc) for doc in cursor]
        except Exception as e:
            raise ServiceError(
                message=f"Failed to list items from MongoDB: {e}", detail=str(e)
            ) from e

    async def find_by_field(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        page_number: int | None = None,
        sort_by: dict[str, int] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> builtins.list[T]:
        """
        Find documents by a given field.
        Maps _id to .id for each returned item.

        Note: If searching by 'id', this automatically maps to '_id' for MongoDB.

        Args:
            field_name: The field name to search by
            field_value: The value to search for
            limit: Optional limit on the number of documents to return
            sort_by: Optional dictionary for sorting, e.g. {"timestamp": 1} for ascending or {"timestamp": -1} for descending
        """
        try:
            # Map 'id' field to '_id' for MongoDB if needed
            mongo_field_name = "_id" if field_name == "id" else field_name
            mongo_field_value = field_value

            # Convert id string to ObjectId if searching by _id
            if mongo_field_name == "_id" and isinstance(mongo_field_value, str):
                try:
                    mongo_field_value = ObjectId(mongo_field_value)
                except Exception:
                    pass

            # Create a cursor
            query: dict[str, Any] = {mongo_field_name: mongo_field_value}
            if filters:
                query.update(filters)

            cursor = self.collection.find(query)

            # Apply sorting
            sort_by_items = list(sort_by.items()) if sort_by else []
            # Use ID for tiebreaking
            sort_by_items.append(("_id", 1))
            cursor = cursor.sort(sort_by_items)

            # Apply limit if specified
            limit = limit or DEFAULT_PAGE_LIMIT
            cursor = cursor.limit(limit)

            # Apply page number if specified
            if page_number is not None and page_number < 1:
                raise ClientError("Page number must be greater than 0")
            if page_number is not None:
                cursor = cursor.skip((page_number - 1) * limit)

            return [self._deserialize(doc) for doc in cursor]
        except Exception as e:
            raise ServiceError(
                message=f"Failed to find items by field in MongoDB: {e}", detail=str(e)
            ) from e

    async def find_by_field_with_cursor(
        self,
        field_name: str,
        field_value: Any,
        limit: int | None = None,
        sort_by: dict[str, int] | None = None,
        before_id: str | None = None,
        after_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> builtins.list[T]:
        """
        Find documents by a given field with cursor-based pagination.
        Maps _id to .id for each returned item.

        Args:
            field_name: The field name to search by
            field_value: The value to search for
            limit: Optional limit on the number of documents to return
            sort_by: Optional dictionary for sorting, e.g. {"created_at": -1} for descending
            before_id: Get documents created before this document ID
            after_id: Get documents created after this document ID

        Note:
            Cursor pagination uses the created_at timestamp of the cursor document
            to filter results. This provides stable pagination even when new
            documents are added.
        """
        try:
            # Map 'id' field to '_id' for MongoDB if needed
            mongo_field_name = "_id" if field_name == "id" else field_name
            mongo_field_value = field_value

            # Convert id string to ObjectId if searching by _id
            if mongo_field_name == "_id" and isinstance(mongo_field_value, str):
                try:
                    mongo_field_value = ObjectId(mongo_field_value)
                except Exception:
                    pass

            # Build base query
            query: dict[str, Any] = {mongo_field_name: mongo_field_value}

            if filters:
                query.update(filters)
            # If cursor is provided, look up the cursor document's timestamp
            # Use compound comparison (created_at, _id) to handle timestamp ties
            if before_id or after_id:
                cursor_id = before_id or after_id
                try:
                    cursor_object_id = ObjectId(cursor_id)
                except Exception:
                    cursor_object_id = cursor_id

                cursor_doc = self.collection.find_one({"_id": cursor_object_id})
                if cursor_doc and "created_at" in cursor_doc:
                    cursor_timestamp = cursor_doc["created_at"]
                    if before_id:
                        # Get documents where (for descending created_at, ascending _id sort):
                        # - created_at < cursor_timestamp (strictly older), OR
                        # - created_at == cursor_timestamp AND _id > cursor_id (same timestamp,
                        #   but later in ascending _id order, i.e., comes after cursor in results)
                        query["$or"] = [
                            {"created_at": {"$lt": cursor_timestamp}},
                            {
                                "created_at": cursor_timestamp,
                                "_id": {"$gt": cursor_object_id},
                            },
                        ]
                    else:  # after_id
                        # Get documents where (for descending created_at, ascending _id sort):
                        # - created_at > cursor_timestamp (strictly newer), OR
                        # - created_at == cursor_timestamp AND _id < cursor_id (same timestamp,
                        #   but earlier in ascending _id order, i.e., comes before cursor in results)
                        query["$or"] = [
                            {"created_at": {"$gt": cursor_timestamp}},
                            {
                                "created_at": cursor_timestamp,
                                "_id": {"$lt": cursor_object_id},
                            },
                        ]

            # Create a cursor
            db_cursor = self.collection.find(query)

            # Apply sorting
            sort_by_items = list(sort_by.items()) if sort_by else []
            # Use ID for tiebreaking
            sort_by_items.append(("_id", 1))
            db_cursor = db_cursor.sort(sort_by_items)

            # Apply limit if specified
            limit = limit or DEFAULT_PAGE_LIMIT
            db_cursor = db_cursor.limit(limit)

            return [self._deserialize(doc) for doc in db_cursor]
        except Exception as e:
            raise ServiceError(
                message=f"Failed to find items by field with cursor in MongoDB: {e}",
                detail=str(e),
            ) from e

    @retry_write_operation()
    async def delete_by_field(self, field_name: str, field_value: Any) -> int:
        """
        Delete documents by a given field.
        Returns the number of documents deleted.

        Note: If deleting by 'id', this automatically maps to '_id' for MongoDB.
        """
        try:
            # Map 'id' field to '_id' for MongoDB if needed
            mongo_field_name = "_id" if field_name == "id" else field_name
            mongo_field_value = field_value

            # Convert id string to ObjectId if deleting by _id
            if mongo_field_name == "_id" and isinstance(mongo_field_value, str):
                try:
                    mongo_field_value = ObjectId(mongo_field_value)
                except Exception:
                    pass

            result = self.collection.delete_many({mongo_field_name: mongo_field_value})
            return result.deleted_count
        except Exception as e:
            raise ServiceError(
                message=f"Failed to delete items by field in MongoDB: {e}",
                detail=str(e),
            ) from e
