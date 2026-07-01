from typing import Any

from fastapi import APIRouter, Query, Request

from src.api.schemas.agent_run_schedules import (
    AgentRunScheduleListResponse,
    AgentRunScheduleResponse,
    CreateAgentRunScheduleRequest,
    PauseRunScheduleRequest,
    ResumeRunScheduleRequest,
    UpdateAgentRunScheduleRequest,
)
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.delete_response import DeleteResponse
from src.domain.services.agent_run_schedule_service import (
    build_run_schedule_authz_selector,
)
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.use_cases.agent_run_schedules_use_case import (
    DAgentRunSchedulesUseCase,
)
from src.domain.use_cases.agents_use_case import DAgentsUseCase
from src.utils.authorization_shortcuts import DAuthorizedId, DAuthorizedResourceIds
from src.utils.logging import make_logger
from src.utils.schedule_authorization import _check_schedule_or_collapse_to_404

logger = make_logger(__name__)

# The canonical agent scheduling API. Schedules an agent *run* on each fire
# (creates a fresh task + delivers the configured initial input), hiding the
# underlying Temporal workflow/task-queue details. It replaced the
# earlier bare-workflow scheduler that previously owned this path.
router = APIRouter(
    prefix="/agents/{agent_id}/schedules",
    tags=["Schedules"],
)

_CREATOR_PRINCIPAL_FIELDS = (
    "principal_type",
    "user_id",
    "service_account_id",
    "account_id",
)


def _extract_creator_principal(principal_context: Any) -> dict[str, Any]:
    """Capture the credential-free creator subset from the request principal.

    Stores only identity selectors (principal_type / user_id / service_account_id
    / account_id). Never cookies, JWTs, API keys, OAuth tokens, or headers.
    Returns an empty dict under authz bypass / when no principal is present.
    """
    if principal_context is None:
        return {}
    if isinstance(principal_context, dict):
        getter = principal_context.get
    else:
        getter = lambda key: getattr(principal_context, key, None)  # noqa: E731
    return {
        field: getter(field)
        for field in _CREATOR_PRINCIPAL_FIELDS
        if getter(field) is not None
    }


@router.post(
    "",
    response_model=AgentRunScheduleResponse,
    summary="Create Run Schedule",
    description="Create a recurring schedule that starts a fresh agent run on each fire.",
)
async def create_run_schedule(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.update),
    request: CreateAgentRunScheduleRequest,
    http_request: Request,
    agents_use_case: DAgentsUseCase,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
) -> AgentRunScheduleResponse:
    """Create a run schedule for an agent.

    Gated on ``agent.update`` (no schedule resource exists yet), mirroring the
    bare-workflow scheduler's create gate. The authenticated creator principal is
    captured here and replayed for AuthZ / task ownership when the schedule fires.
    """
    agent = await agents_use_case.get(id=agent_id)
    creator_principal = _extract_creator_principal(
        getattr(http_request.state, "principal_context", None)
    )
    return await run_schedules_use_case.create_schedule(
        agent, request, creator_principal
    )


@router.get(
    "",
    response_model=AgentRunScheduleListResponse,
    summary="List Run Schedules",
    description="List run schedules for an agent.",
)
async def list_run_schedules(
    agent_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorized_schedule_ids: DAuthorizedResourceIds(AgentexResourceType.schedule),
    limit: int = Query(default=100, ge=1, le=1000),
) -> AgentRunScheduleListResponse:
    """List an agent's run schedules, filtered to those the caller owns.

    Filter-only (never 403s): ``authorized_schedule_ids`` is ``None`` under authz
    bypass (return all), else the set of readable selectors (empty returns none).
    """
    return await run_schedules_use_case.list_schedules(
        agent_id,
        authorized_schedule_ids=authorized_schedule_ids,
        limit=limit,
    )


@router.get(
    "/{name}",
    response_model=AgentRunScheduleResponse,
    summary="Get Run Schedule",
    description="Get a run schedule by its name.",
)
async def get_run_schedule(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, name),
        AuthorizedOperationType.read,
    )
    return await run_schedules_use_case.get_schedule(agent_id, name)


@router.patch(
    "/{name}",
    response_model=AgentRunScheduleResponse,
    summary="Update Run Schedule",
    description="Partially update a run schedule's definition (cadence, window, input, etc.).",
)
async def update_run_schedule(
    agent_id: str,
    name: str,
    request: UpdateAgentRunScheduleRequest,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, name),
        AuthorizedOperationType.update,
    )
    return await run_schedules_use_case.update_schedule(agent_id, name, request)


@router.post(
    "/{name}/trigger",
    response_model=AgentRunScheduleResponse,
    summary="Trigger Run Schedule",
    description="Trigger an immediate, out-of-band run of the schedule (in addition to its cadence).",
)
async def trigger_run_schedule(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, name),
        AuthorizedOperationType.update,
    )
    return await run_schedules_use_case.trigger_schedule(agent_id, name)


@router.post(
    "/{name}/pause",
    response_model=AgentRunScheduleResponse,
    summary="Pause Run Schedule",
    description="Pause a run schedule so it stops firing.",
)
async def pause_run_schedule(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: PauseRunScheduleRequest | None = None,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, name),
        AuthorizedOperationType.update,
    )
    note = request.note if request else None
    return await run_schedules_use_case.pause_schedule(agent_id, name, note=note)


@router.post(
    "/{name}/resume",
    response_model=AgentRunScheduleResponse,
    summary="Resume Run Schedule",
    description="Resume a paused run schedule so it fires again.",
)
async def resume_run_schedule(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: ResumeRunScheduleRequest | None = None,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, name),
        AuthorizedOperationType.update,
    )
    note = request.note if request else None
    return await run_schedules_use_case.resume_schedule(agent_id, name, note=note)


@router.delete(
    "/{name}",
    response_model=DeleteResponse,
    summary="Delete Run Schedule",
    description="Delete a run schedule permanently.",
)
async def delete_run_schedule(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> DeleteResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, name),
        AuthorizedOperationType.delete,
    )
    schedule_id = await run_schedules_use_case.delete_schedule(agent_id, name)
    return DeleteResponse(
        id=schedule_id,
        message=f"Run schedule '{name}' deleted successfully",
    )
