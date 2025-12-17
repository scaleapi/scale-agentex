from typing import Annotated, Any, Literal

from fastapi import Depends

from src.domain.entities.task_messages import (
    TaskMessageContentEntity,
    TaskMessageEntity,
    TaskMessageEntityFilter,
)
from src.domain.services.task_message_service import DTaskMessageService


def convert_filters_to_mongodb_query(
    filters: TaskMessageEntityFilter,
) -> dict[str, Any]:
    """
    Convert TaskMessageEntityFilter to MongoDB query dict.

    Flattens nested objects to dot notation for MongoDB queries.
    e.g., {"content": {"type": "text"}} -> {"content.type": "text"}
    """

    def flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(flatten(value, full_key))
            else:
                result[full_key] = value
        return result

    data = filters.model_dump(exclude_none=True)
    return flatten(data)


class MessagesUseCase:
    def __init__(
        self,
        task_message_service: DTaskMessageService,
    ):
        self.task_message_service = task_message_service

    async def create(
        self,
        task_id: str,
        content: TaskMessageContentEntity,
        streaming_status: Literal["IN_PROGRESS", "DONE"] | None,
    ) -> TaskMessageEntity:
        """
        Create a new message for a task.

        Args:
            task_id: The task ID
            content: The task message content to create

        Returns:
            The created TaskMessageEntity with ID and metadata
        """
        return await self.task_message_service.append_message(
            task_id=task_id,
            content=content,
            streaming_status=streaming_status,
        )

    async def update(
        self,
        task_id: str,
        message_id: str,
        content: TaskMessageContentEntity,
        streaming_status: Literal["IN_PROGRESS", "DONE"] | None,
    ) -> TaskMessageEntity:
        """
        Update a message for a task.

        Args:
            task_id: The task ID
            message_id: The message ID
            content: The task message content to update

        """
        return await self.task_message_service.update_message(
            task_id=task_id,
            message_id=message_id,
            content=content,
            streaming_status=streaming_status,
        )

    async def create_batch(
        self, task_id: str, contents: list[TaskMessageContentEntity]
    ) -> list[TaskMessageEntity]:
        """
        Create multiple messages for a task.

        Args:
            task_id: The task ID
            messages: The messages to create

        Returns:
            The created TaskMessageEntity objects with IDs and metadata
        """
        return await self.task_message_service.append_messages(
            task_id=task_id,
            contents=contents,
        )

    async def update_batch(
        self, task_id: str, updates: dict[str, TaskMessageContentEntity]
    ) -> list[TaskMessageEntity]:
        """
        Update multiple messages for a task.
        """
        return await self.task_message_service.update_messages(
            task_id=task_id, updates=updates
        )

    async def get_message(self, message_id: str) -> TaskMessageEntity | None:
        """
        Get a message by its ID.

        Args:
            message_id: The message ID

        Returns:
            The TaskMessageEntity if found, None otherwise
        """
        return await self.task_message_service.get_message(message_id=message_id)

    async def list_messages(
        self,
        task_id: str,
        limit: int,
        page_number: int,
        order_by: str | None = None,
        order_direction: str = "desc",
        before_id: str | None = None,
        after_id: str | None = None,
        filters: TaskMessageEntityFilter | None = None,
    ) -> list[TaskMessageEntity]:
        """
        Get all messages for a task with optional cursor-based pagination.

        Args:
            task_id: The task ID
            limit: Maximum number of messages to return
            page_number: Page number for offset-based pagination
            order_by: Field name to order by (defaults to created_at)
            order_direction: Direction to order by ("asc" or "desc", defaults to "desc")
            before_id: Get messages created before this message ID (cursor pagination)
            after_id: Get messages created after this message ID (cursor pagination)

        Returns:
            List of TaskMessageEntity objects for the task

        Note:
            When using before_id or after_id, page_number is ignored.
        """
        converted_filters = (
            convert_filters_to_mongodb_query(filters) if filters else None
        )
        return await self.task_message_service.get_messages(
            task_id=task_id,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
            before_id=before_id,
            after_id=after_id,
            filters=converted_filters,
        )


DMessageUseCase = Annotated[MessagesUseCase, Depends(MessagesUseCase)]
