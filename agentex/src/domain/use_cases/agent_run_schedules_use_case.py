from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends

from src.api.schemas.agent_run_schedules import (
    AgentRunScheduleListResponse,
    AgentRunScheduleResponse,
    CreateAgentRunScheduleRequest,
    UpdateAgentRunScheduleRequest,
)
from src.domain.entities.agents import AgentEntity
from src.domain.services.agent_run_schedule_service import DAgentRunScheduleService
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentRunSchedulesUseCase:
    """Use case for managing scheduled agent runs."""

    def __init__(
        self,
        run_schedule_service: DAgentRunScheduleService,
    ):
        self.run_schedule_service = run_schedule_service

    async def create_schedule(
        self,
        agent: AgentEntity,
        request: CreateAgentRunScheduleRequest,
        creator_principal: dict[str, Any],
    ) -> AgentRunScheduleResponse:
        # Cadence mutual-exclusivity is enforced on the request models
        # (CreateAgentRunScheduleRequest / UpdateAgentRunScheduleRequest).
        return await self.run_schedule_service.create_schedule(
            agent, request, creator_principal
        )

    async def list_schedules(
        self,
        agent_id: str,
        authorized_schedule_ids: list[str] | None = None,
        limit: int = 100,
    ) -> AgentRunScheduleListResponse:
        return await self.run_schedule_service.list_schedules(
            agent_id,
            authorized_schedule_ids=authorized_schedule_ids,
            limit=limit,
        )

    async def get_schedule(
        self, agent_id: str, schedule_id: str
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.get_schedule(agent_id, schedule_id)

    async def get_schedule_id_by_name(self, agent_id: str, name: str) -> str:
        return await self.run_schedule_service.get_schedule_id_by_name(agent_id, name)

    async def pause_schedule(
        self, agent_id: str, schedule_id: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.pause_schedule(
            agent_id, schedule_id, note=note
        )

    async def resume_schedule(
        self, agent_id: str, schedule_id: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.resume_schedule(
            agent_id, schedule_id, note=note
        )

    async def update_schedule(
        self, agent_id: str, schedule_id: str, request: UpdateAgentRunScheduleRequest
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.update_schedule(
            agent_id, schedule_id, request
        )

    async def trigger_schedule(
        self, agent_id: str, schedule_id: str
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.trigger_schedule(agent_id, schedule_id)

    async def skip_schedule_action(
        self, agent_id: str, schedule_id: str, scheduled_time: datetime
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.skip_schedule_action(
            agent_id, schedule_id, scheduled_time=scheduled_time
        )

    async def unskip_schedule_action(
        self, agent_id: str, schedule_id: str, scheduled_time: datetime
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.unskip_schedule_action(
            agent_id, schedule_id, scheduled_time=scheduled_time
        )

    async def delete_schedule(self, agent_id: str, schedule_id: str) -> str:
        return await self.run_schedule_service.delete_schedule(agent_id, schedule_id)


DAgentRunSchedulesUseCase = Annotated[
    AgentRunSchedulesUseCase, Depends(AgentRunSchedulesUseCase)
]
