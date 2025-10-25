from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends

from src.domain.entities.task_messages import (
    TaskMessageContentEntity,
    TaskMessageEntity,
)
from src.domain.repositories.task_message_repository import DTaskMessageRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskMessageService:
    """
    Service for handling task message operations.
    """

    def __init__(self, message_repository: DTaskMessageRepository):
        """
        Initialize the service with required dependencies.

        Args:
            message_repository: Repository for storing and retrieving messages
        """
        self.repository = message_repository

    async def get_message(self, message_id: str) -> TaskMessageEntity:
        """
        Get message by ID.

        Args:
            message_id: The message ID to get

        Returns:
            The TaskMessageEntity object

        Raises:
            ItemDoesNotExist: If the message with the given ID does not exist
        """
        return await self.repository.get(id=message_id)

    async def get_messages(
        self, task_id: str, limit: int, page_number: int
    ) -> list[TaskMessageEntity]:
        """
        Get all messages for a specific task.

        Args:
            task_id: The task ID
            limit: Optional limit on the number of messages to return

        Returns:
            List of TaskMessageEntity objects for the task
        """
        # Sort by created_at in ascending order (oldest first)
        # This is typically what we want for conversation history
        return await self.repository.find_by_field(
            "task_id",
            task_id,
            limit=limit,
            page_number=page_number,
            sort_by={"created_at": 1},
        )

    async def append_message(
        self,
        task_id: str,
        content: TaskMessageContentEntity,
        streaming_status: Literal["IN_PROGRESS", "DONE"] | None = None,
    ) -> TaskMessageEntity:
        """
        Append a message to the task's message list.

        Args:
            task_id: The task ID
            message: The message to append

        Returns:
            The created TaskMessageEntity with ID and metadata
        """
        task_message = TaskMessageEntity(
            task_id=task_id,
            content=content,
            streaming_status=streaming_status,
        )

        return await self.repository.create(task_message)

    async def append_messages(
        self,
        task_id: str,
        contents: list[TaskMessageContentEntity],
        streaming_status: Literal["IN_PROGRESS", "DONE"] | None = None,
    ) -> list[TaskMessageEntity]:
        """
        Append multiple messages to the task's message list.

        Args:
            task_id: The task ID
            messages: The messages to append

        Returns:
            The created TaskMessageEntity objects with IDs and metadata
        """
        # Add a small time increment to each message to ensure unique ordering
        current_time = datetime.now(UTC)

        task_messages = []
        for i, message in enumerate(contents):
            # Add i microseconds to ensure unique timestamps within the batch
            adjusted_time = current_time + timedelta(microseconds=i)
            task_message = TaskMessageEntity(
                task_id=task_id,
                content=message,
                streaming_status=streaming_status,
                created_at=adjusted_time,
                updated_at=adjusted_time,
            )
            task_messages.append(task_message)

        created_messages = await self.repository.batch_create(task_messages)
        logger.info(f"Created batch of messages: {created_messages}")
        return created_messages

    async def update_message(
        self,
        task_id: str,
        message_id: str,
        content: TaskMessageContentEntity,
        streaming_status: Literal["IN_PROGRESS", "DONE"] | None,
    ) -> TaskMessageEntity | None:
        """
        Update a message by its ID.

        Args:
            task_id: The task ID
            message_id: The message ID
            message: The updated message

        Returns:
            The updated TaskMessageEntity if found, None otherwise
        """
        # First get the existing task message
        task_message = await self.repository.get(id=message_id)

        if task_message and task_message.task_id == task_id:
            # Update the message field but preserve other fields
            task_message.content = content
            if streaming_status is not None:
                task_message.streaming_status = streaming_status
            return await self.repository.update(task_message)
        return None

    async def update_messages(
        self, task_id: str, updates: dict[str, TaskMessageContentEntity]
    ) -> list[TaskMessageEntity]:
        """
        Update multiple messages by their IDs.

        Args:
            task_id: The task ID
            updates: Dictionary mapping message IDs to updated messages

        Returns:
            List of updated TaskMessageEntity objects
        """
        updated_messages = []
        for message_id, message in updates.items():
            # Get the existing task message
            task_message = await self.repository.get(id=message_id)
            if task_message and task_message.task_id == task_id:
                # Update the message field but preserve other fields
                task_message.content = message
                updated_messages.append(await self.repository.update(task_message))

        return updated_messages

    async def delete_message(self, task_id: str, message_id: str) -> bool:
        """
        Delete a message by its ID.

        Args:
            task_id: The task ID
            message_id: The message ID

        Returns:
            True if deleted, False otherwise
        """
        # First check if the message exists and belongs to the task
        task_message = await self.repository.get(id=message_id)
        if task_message and task_message.task_id == task_id:
            await self.repository.delete(id=message_id)
            return True
        return False

    async def delete_messages(self, task_id: str, message_ids: list[str]) -> int:
        """
        Delete multiple messages by their IDs.

        Args:
            task_id: The task ID
            message_ids: List of message IDs

        Returns:
            Number of messages deleted
        """
        # First check which messages exist and belong to the task
        valid_ids = []
        for message_id in message_ids:
            task_message = await self.repository.get(id=message_id)
            if task_message and task_message.task_id == task_id:
                valid_ids.append(message_id)

        if valid_ids:
            await self.repository.batch_delete(ids=valid_ids)
        return len(valid_ids)

    async def delete_all_messages(self, task_id: str) -> int:
        """
        Delete all messages for a specific task.

        Args:
            task_id: The task ID

        Returns:
            Number of messages deleted
        """
        return await self.repository.delete_by_field("task_id", task_id)


DTaskMessageService = Annotated[TaskMessageService, Depends(TaskMessageService)]
