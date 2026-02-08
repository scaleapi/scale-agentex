from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends


class StreamRepository(ABC):
    """
    Interface for event streaming repositories.
    Used to publish and subscribe to event streams.
    """

    @abstractmethod
    async def send_data(self, topic: str, data: dict[str, Any]) -> str:
        """
        Send an event to a stream.

        Args:
            topic: The stream topic/name
            event: The event data

        Returns:
            The message ID or other identifier
        """
        raise NotImplementedError

    @abstractmethod
    async def read_messages(
        self, topic: str, last_id: str, timeout_ms: int = 2000, count: int = 10
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """
        Read messages from a stream and yield them one by one.

        Args:
            topic: The stream topic to read from
            last_id: Where to start reading from
            timeout_ms: How long to block waiting for new messages (in milliseconds)
            count: Maximum number of messages to read

        Yields:
            Tuples of (message_id, event_data) for each message
        """
        raise NotImplementedError

    @abstractmethod
    async def cleanup_stream(self, topic: str) -> None:
        """
        Clean up a stream.

        Args:
            topic: The stream topic to clean up
        """
        raise NotImplementedError


DStreamRepository = Annotated[StreamRepository | None, Depends(StreamRepository)]
