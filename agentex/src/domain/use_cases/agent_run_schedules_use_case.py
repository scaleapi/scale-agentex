from typing import Annotated, Any

from fastapi import Depends

from src.api.schemas.agent_run_schedules import (
    AgentRunScheduleListResponse,
    AgentRunScheduleResponse,
    CreateAgentRunScheduleRequest,
    UpdateAgentRunScheduleRequest,
)
from src.domain.entities.agents import AgentEntity
from src.domain.exceptions import ClientError
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
        if not request.cron_expression and not request.interval_seconds:
            raise ClientError(
                "Either cron_expression or interval_seconds must be provided"
            )
        if request.cron_expression and request.interval_seconds:
            raise ClientError(
                "Provide only one of cron_expression or interval_seconds, not both"
            )
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

    async def get_schedule(self, agent_id: str, name: str) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.get_schedule(agent_id, name)

    async def pause_schedule(
        self, agent_id: str, name: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.pause_schedule(agent_id, name, note=note)

    async def resume_schedule(
        self, agent_id: str, name: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.resume_schedule(
            agent_id, name, note=note
        )

    async def update_schedule(
        self, agent_id: str, name: str, request: UpdateAgentRunScheduleRequest
    ) -> AgentRunScheduleResponse:
        if request.cron_expression and request.interval_seconds:
            raise ClientError(
                "Provide only one of cron_expression or interval_seconds, not both"
            )
        return await self.run_schedule_service.update_schedule(agent_id, name, request)

    async def trigger_schedule(
        self, agent_id: str, name: str
    ) -> AgentRunScheduleResponse:
        return await self.run_schedule_service.trigger_schedule(agent_id, name)

    async def delete_schedule(self, agent_id: str, name: str) -> str:
        return await self.run_schedule_service.delete_schedule(agent_id, name)


DAgentRunSchedulesUseCase = Annotated[
    AgentRunSchedulesUseCase, Depends(AgentRunSchedulesUseCase)
]
