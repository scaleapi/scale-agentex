from fastapi import APIRouter, Query, Response

from src.api.cache import cacheable
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.delete_response import DeleteResponse
from src.api.schemas.schedules import (
    CreateScheduleRequest,
    PauseScheduleRequest,
    ScheduleListResponse,
    ScheduleResponse,
    UnpauseScheduleRequest,
)
from src.domain.use_cases.agents_use_case import DAgentsUseCase
from src.domain.use_cases.schedules_use_case import DSchedulesUseCase
from src.utils.authorization_shortcuts import DAuthorizedId
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(
    prefix="/agents/{agent_id}/schedules",
    tags=["Schedules"],
)


@router.post(
    "",
    response_model=ScheduleResponse,
    summary="Create Schedule",
    description="Create a new schedule for recurring workflow execution for an agent.",
)
async def create_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    request: CreateScheduleRequest,
    agents_use_case: DAgentsUseCase,
    schedules_use_case: DSchedulesUseCase,
) -> ScheduleResponse:
    """Create a new schedule for an agent's workflow."""
    agent = await agents_use_case.get(id=agent_id)
    return await schedules_use_case.create_schedule(agent, request)


@router.get(
    "",
    response_model=ScheduleListResponse,
    summary="List Agent Schedules",
    description="List all schedules for an agent.",
)
@cacheable(max_age=60)
async def list_schedules(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.read),
    schedules_use_case: DSchedulesUseCase,
    response: Response,
    page_size: int = Query(default=100, ge=1, le=1000),
) -> ScheduleListResponse:
    """List all schedules for an agent."""
    return await schedules_use_case.list_schedules(agent_id, page_size=page_size)


@router.get(
    "/{schedule_name}",
    response_model=ScheduleResponse,
    summary="Get Schedule",
    description="Get details of a schedule by its name.",
)
@cacheable(max_age=60)
async def get_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.read),
    schedule_name: str,
    schedules_use_case: DSchedulesUseCase,
    response: Response,
) -> ScheduleResponse:
    """Get details of a schedule."""
    return await schedules_use_case.get_schedule(agent_id, schedule_name)


@router.post(
    "/{schedule_name}/pause",
    response_model=ScheduleResponse,
    summary="Pause Schedule",
    description="Pause a schedule to stop it from executing.",
)
async def pause_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    schedule_name: str,
    schedules_use_case: DSchedulesUseCase,
    request: PauseScheduleRequest | None = None,
) -> ScheduleResponse:
    """Pause a schedule."""
    note = request.note if request else None
    return await schedules_use_case.pause_schedule(agent_id, schedule_name, note=note)


@router.post(
    "/{schedule_name}/unpause",
    response_model=ScheduleResponse,
    summary="Unpause Schedule",
    description="Unpause/resume a schedule to allow it to execute again.",
)
async def unpause_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    schedule_name: str,
    schedules_use_case: DSchedulesUseCase,
    request: UnpauseScheduleRequest | None = None,
) -> ScheduleResponse:
    """Unpause/resume a schedule."""
    note = request.note if request else None
    return await schedules_use_case.unpause_schedule(agent_id, schedule_name, note=note)


@router.post(
    "/{schedule_name}/trigger",
    response_model=ScheduleResponse,
    summary="Trigger Schedule",
    description="Trigger a schedule to run immediately, regardless of its regular schedule.",
)
async def trigger_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    schedule_name: str,
    schedules_use_case: DSchedulesUseCase,
) -> ScheduleResponse:
    """Trigger a schedule to run immediately."""
    return await schedules_use_case.trigger_schedule(agent_id, schedule_name)


@router.delete(
    "/{schedule_name}",
    response_model=DeleteResponse,
    summary="Delete Schedule",
    description="Delete a schedule permanently.",
)
async def delete_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.delete),
    schedule_name: str,
    schedules_use_case: DSchedulesUseCase,
) -> DeleteResponse:
    """Delete a schedule."""
    await schedules_use_case.delete_schedule(agent_id, schedule_name)
    return DeleteResponse(
        id=f"{agent_id}--{schedule_name}",
        message=f"Schedule '{schedule_name}' deleted successfully",
    )
