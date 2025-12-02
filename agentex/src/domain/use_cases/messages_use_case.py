from typing import Annotated, Literal

from fastapi import Depends

from src.domain.entities.task_messages import (
    TaskMessageContentEntity,
    TaskMessageEntity,
)
from src.domain.services.task_message_service import DTaskMessageService
from src.utils.logging import make_logger

logger = make_logger(__name__)


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
    ) -> list[TaskMessageEntity]:
        """
        Get all messages for a task.

        Args:
            task_id: The task ID
            limit: Optional limit on the number of messages to return
            order_by: Optional field name to order by (defaults to created_at)
            order_direction: Optional direction to order by ("asc" or "desc", defaults to "desc")

        Returns:
            List of TaskMessageEntity objects for the task
        """
        return await self.task_message_service.get_messages(
            task_id=task_id,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )


DMessageUseCase = Annotated[MessagesUseCase, Depends(MessagesUseCase)]
