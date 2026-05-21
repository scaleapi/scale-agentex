from typing import Annotated

from fastapi import Depends

from src.api.schemas.schedules import (
    CreateScheduleRequest,
    ScheduleListResponse,
    ScheduleResponse,
)
from src.domain.entities.agents import AgentEntity
from src.domain.exceptions import ClientError
from src.domain.services.schedule_service import DScheduleService
from src.utils.logging import make_logger

logger = make_logger(__name__)


class SchedulesUseCase:
    """
    Use case for managing Temporal schedules scoped to agents.
    """

    def __init__(
        self,
        schedule_service: DScheduleService,
    ):
        self.schedule_service = schedule_service

    async def create_schedule(
        self,
        agent: AgentEntity,
        request: CreateScheduleRequest,
    ) -> ScheduleResponse:
        """
        Create a new schedule for recurring workflow execution.

        Args:
            agent: The agent this schedule belongs to
            request: The schedule creation request

        Returns:
            ScheduleResponse with the created schedule details

        Raises:
            ClientError: If neither cron_expression nor interval_seconds is provided
        """
        if not request.cron_expression and not request.interval_seconds:
            raise ClientError(
                "Either cron_expression or interval_seconds must be provided"
            )

        return await self.schedule_service.create_schedule(agent, request)

    async def get_schedule(self, agent_id: str, schedule_name: str) -> ScheduleResponse:
        """
        Get details of a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name

        Returns:
            ScheduleResponse with schedule details
        """
        return await self.schedule_service.get_schedule(agent_id, schedule_name)

    async def list_schedules(
        self, agent_id: str, page_size: int = 100
    ) -> ScheduleListResponse:
        """
        List schedules for an agent.

        Args:
            agent_id: The agent ID
            page_size: Number of results to return

        Returns:
            ScheduleListResponse with list of schedules
        """
        return await self.schedule_service.list_schedules(
            agent_id=agent_id, page_size=page_size
        )

    async def pause_schedule(
        self, agent_id: str, schedule_name: str, note: str | None = None
    ) -> ScheduleResponse:
        """
        Pause a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name
            note: Optional note explaining why the schedule was paused

        Returns:
            ScheduleResponse with updated schedule details
        """
        return await self.schedule_service.pause_schedule(
            agent_id, schedule_name, note=note
        )

    async def unpause_schedule(
        self, agent_id: str, schedule_name: str, note: str | None = None
    ) -> ScheduleResponse:
        """
        Unpause/resume a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name
            note: Optional note explaining why the schedule was unpaused

        Returns:
            ScheduleResponse with updated schedule details
        """
        return await self.schedule_service.unpause_schedule(
            agent_id, schedule_name, note=note
        )

    async def trigger_schedule(
        self, agent_id: str, schedule_name: str
    ) -> ScheduleResponse:
        """
        Trigger a schedule to run immediately.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name

        Returns:
            ScheduleResponse with updated schedule details
        """
        return await self.schedule_service.trigger_schedule(agent_id, schedule_name)

    async def delete_schedule(self, agent_id: str, schedule_name: str) -> None:
        """
        Delete a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name
        """
        await self.schedule_service.delete_schedule(agent_id, schedule_name)


DSchedulesUseCase = Annotated[SchedulesUseCase, Depends(SchedulesUseCase)]
