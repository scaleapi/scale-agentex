from typing import Annotated

from fastapi import Depends

from src.domain.entities.agent_task_tracker import AgentTaskTrackerEntity
from src.domain.exceptions import ClientError
from src.domain.repositories.agent_task_tracker_repository import (
    DAgentTaskTrackerRepository,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentTaskTrackerUseCase:
    def __init__(self, tracker_repository: DAgentTaskTrackerRepository):
        self._tracker_repository = tracker_repository

    async def get_agent_task_tracker(self, tracker_id: str) -> AgentTaskTrackerEntity:
        """
        Get agent task tracker for a specific agent and task.
        """
        return await self._tracker_repository.get(id=tracker_id)

    async def list(
        self, agent_id: str | None = None, task_id: str | None = None
    ) -> list[AgentTaskTrackerEntity]:
        """
        List agent task trackers.
        """
        if agent_id and task_id:
            return await self._tracker_repository.list(
                filters={"agent_id": agent_id, "task_id": task_id}
            )
        elif agent_id:
            return await self._tracker_repository.list(filters={"agent_id": agent_id})
        elif task_id:
            return await self._tracker_repository.list(filters={"task_id": task_id})
        else:
            return await self._tracker_repository.list()

    async def update_agent_task_tracker(
        self,
        tracker_id: str,
        last_processed_event_id: str | None = None,
        status: str | None = None,
        status_reason: str | None = None,
    ) -> AgentTaskTrackerEntity:
        """
        Commit cursor position for an agent-task combination.

        Args:
            agent_id: The agent ID
            task_id: The task ID
            last_processed_event_id: The last processed event ID (None to leave unchanged)
            status: Processing status
            status_reason: Optional status reason

        Returns:
            Updated AgentTaskTrackerEntity object

        Raises:
            ClientError: If invalid parameters or cursor moves backwards
        """
        # Validate inputs
        try:
            # Commit the cursor
            updated_state = await self._tracker_repository.update_agent_task_tracker(
                id=tracker_id,
                status=status,
                status_reason=status_reason,
                last_processed_event_id=last_processed_event_id,
            )

            if last_processed_event_id is not None:
                logger.info(
                    f"Committed cursor for tracker {tracker_id} to event {last_processed_event_id}"
                )
            else:
                logger.info(
                    f"Updated processing state for tracker {tracker_id} (cursor unchanged)"
                )

            return updated_state
        except ValueError as e:
            logger.warning(f"Invalid cursor commit: {e}")
            raise ClientError(str(e)) from e


DAgentTaskTrackerUseCase = Annotated[
    AgentTaskTrackerUseCase, Depends(AgentTaskTrackerUseCase)
]
