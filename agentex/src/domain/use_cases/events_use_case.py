from typing import Annotated

from fastapi import Depends

from src.domain.entities.events import EventEntity
from src.domain.repositories.event_repository import DEventRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)


class EventUseCase:
    def __init__(self, event_repository: DEventRepository):
        self.event_repository = event_repository

    async def get(self, event_id: str) -> EventEntity:
        return await self.event_repository.get(event_id)

    async def list_events_after_last_processed(
        self,
        task_id: str,
        agent_id: str,
        last_processed_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[EventEntity]:
        """
        List events for a specific task and agent, optionally filtering for events
        after a specific sequence ID.

        Args:
            task_id: The task ID to filter by
            agent_id: The agent ID to filter by
            last_processed_event_id: Optional event ID to filter events after
            limit: Optional limit on number of results

        Returns:
            List of Event objects ordered by sequence_id
        """
        return await self.event_repository.list_events_after_last_processed(
            task_id=task_id,
            agent_id=agent_id,
            last_processed_event_id=last_processed_event_id,
            limit=limit,
        )


DEventUseCase = Annotated[EventUseCase, Depends(EventUseCase)]
