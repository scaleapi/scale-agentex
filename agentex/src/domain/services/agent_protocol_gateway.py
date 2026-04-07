from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from src.domain.entities.agents import AgentEntity
from src.domain.entities.events import EventEntity
from src.domain.entities.task_message_updates import TaskMessageUpdateEntity
from src.domain.entities.task_messages import TaskMessageContentEntity
from src.domain.entities.tasks import TaskEntity


class AgentProtocolGateway(ABC):
    """Protocol-neutral interface for communicating with downstream agent servers."""

    @abstractmethod
    async def create_task(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        service_url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new task on the agent server."""
        ...

    @abstractmethod
    async def send_message(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        content: TaskMessageContentEntity,
        service_url: str,
    ) -> TaskMessageContentEntity:
        """Send a message to a running task."""
        ...

    @abstractmethod
    async def send_message_stream(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        content: TaskMessageContentEntity,
        service_url: str,
    ) -> AsyncIterator[TaskMessageUpdateEntity]:
        """Send a message to a running task and stream the response."""
        ...

    @abstractmethod
    async def cancel_task(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        service_url: str,
    ) -> dict[str, Any]:
        """Cancel a running task."""
        ...

    async def send_event(
        self,
        agent: AgentEntity,
        event: EventEntity,
        task: TaskEntity,
        service_url: str,
        request_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send an event to a running task. Not all protocols support events."""
        raise NotImplementedError("This protocol does not support events")

    async def check_health(
        self,
        agent_id: str,
        service_url: str,
    ) -> bool:
        """Check if the agent server is healthy."""
        raise NotImplementedError("This protocol does not support health checks")
