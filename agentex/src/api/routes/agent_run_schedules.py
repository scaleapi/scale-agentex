from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from src.api.schemas.agent_run_schedules import (
    AgentRunScheduleListResponse,
    AgentRunScheduleResponse,
    CreateAgentRunScheduleRequest,
    PauseRunScheduleRequest,
    ResumeRunScheduleRequest,
    SkipRunScheduleRequest,
    UnskipRunScheduleRequest,
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
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    include_live: Annotated[
        bool,
        Query(description="Include live Temporal state and upcoming action times."),
    ] = False,
) -> AgentRunScheduleListResponse:
    """List an agent's run schedules, filtered to those the caller owns.

    Filter-only (never 403s): ``authorized_schedule_ids`` is ``None`` under authz
    bypass (return all), else the set of readable selectors (empty returns none).
    """
    return await run_schedules_use_case.list_schedules(
        agent_id,
        authorized_schedule_ids=authorized_schedule_ids,
        limit=limit,
        include_live=include_live,
    )


async def _resolve_name_alias_and_check(
    agent_id: str,
    name: str,
    operation: AuthorizedOperationType,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> str:
    # Name aliases are per-agent labels, so resolve them under the agent first
    # and then authorize/operate on the immutable schedule id. Acting on the id,
    # not the name, keeps it the stable auth and mutation target even if the
    # label changes, and closes the rename/recreate race where a check on the old
    # row could precede a write that lands on a new one. Both the absent-name and
    # the denied-resource paths raise this same name-based 404 so an unauthorized
    # caller can neither distinguish the two nor read back the resolved id.
    not_found_message = f"Run schedule '{name}' for agent '{agent_id}' does not exist."
    schedule_id = await run_schedules_use_case.get_schedule_id_by_name(agent_id, name)
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        operation,
        not_found_message=not_found_message,
    )
    return schedule_id


@router.get(
    "/name/{name}",
    response_model=AgentRunScheduleResponse,
    summary="Get Run Schedule By Name",
    description="Get a run schedule by its active name.",
)
async def get_run_schedule_by_name(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    schedule_id = await _resolve_name_alias_and_check(
        agent_id,
        name,
        AuthorizedOperationType.read,
        run_schedules_use_case,
        authorization,
    )
    return await run_schedules_use_case.get_schedule(agent_id, schedule_id)


@router.get(
    "/{schedule_id}",
    response_model=AgentRunScheduleResponse,
    summary="Get Run Schedule",
    description="Get a run schedule by its id.",
)
async def get_run_schedule(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.read,
    )
    return await run_schedules_use_case.get_schedule(agent_id, schedule_id)


@router.patch(
    "/name/{name}",
    response_model=AgentRunScheduleResponse,
    summary="Update Run Schedule By Name",
    description="Partially update a run schedule's definition by its active name.",
)
async def update_run_schedule_by_name(
    agent_id: str,
    name: str,
    request: UpdateAgentRunScheduleRequest,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    schedule_id = await _resolve_name_alias_and_check(
        agent_id,
        name,
        AuthorizedOperationType.update,
        run_schedules_use_case,
        authorization,
    )
    return await run_schedules_use_case.update_schedule(agent_id, schedule_id, request)


@router.patch(
    "/{schedule_id}",
    response_model=AgentRunScheduleResponse,
    summary="Update Run Schedule",
    description="Partially update a run schedule's definition (cadence, window, input, etc.).",
)
async def update_run_schedule(
    agent_id: str,
    schedule_id: str,
    request: UpdateAgentRunScheduleRequest,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.update,
    )
    return await run_schedules_use_case.update_schedule(agent_id, schedule_id, request)


@router.post(
    "/name/{name}/trigger",
    response_model=AgentRunScheduleResponse,
    summary="Trigger Run Schedule By Name",
    description="Trigger an immediate, out-of-band run of the schedule by its active name.",
)
async def trigger_run_schedule_by_name(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    schedule_id = await _resolve_name_alias_and_check(
        agent_id,
        name,
        AuthorizedOperationType.update,
        run_schedules_use_case,
        authorization,
    )
    return await run_schedules_use_case.trigger_schedule(agent_id, schedule_id)


@router.post(
    "/{schedule_id}/trigger",
    response_model=AgentRunScheduleResponse,
    summary="Trigger Run Schedule",
    description="Trigger an immediate, out-of-band run of the schedule (in addition to its cadence).",
)
async def trigger_run_schedule(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.update,
    )
    return await run_schedules_use_case.trigger_schedule(agent_id, schedule_id)


@router.post(
    "/{schedule_id}/skip",
    response_model=AgentRunScheduleResponse,
    summary="Skip Run Schedule Action",
    description="Skip a recurring fire of the schedule.",
)
async def skip_run_schedule_action(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: SkipRunScheduleRequest,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.update,
    )
    return await run_schedules_use_case.skip_schedule_action(
        agent_id,
        schedule_id,
        scheduled_time=request.scheduled_time,
    )


@router.post(
    "/{schedule_id}/unskip",
    response_model=AgentRunScheduleResponse,
    summary="Unskip Run Schedule Action",
    description="Remove a skip for a recurring fire of the schedule.",
)
async def unskip_run_schedule_action(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: UnskipRunScheduleRequest,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.update,
    )
    return await run_schedules_use_case.unskip_schedule_action(
        agent_id,
        schedule_id,
        scheduled_time=request.scheduled_time,
    )


@router.post(
    "/name/{name}/pause",
    response_model=AgentRunScheduleResponse,
    summary="Pause Run Schedule By Name",
    description="Pause a run schedule by its active name.",
)
async def pause_run_schedule_by_name(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: PauseRunScheduleRequest | None = None,
) -> AgentRunScheduleResponse:
    schedule_id = await _resolve_name_alias_and_check(
        agent_id,
        name,
        AuthorizedOperationType.update,
        run_schedules_use_case,
        authorization,
    )
    note = request.note if request else None
    return await run_schedules_use_case.pause_schedule(agent_id, schedule_id, note=note)


@router.post(
    "/{schedule_id}/pause",
    response_model=AgentRunScheduleResponse,
    summary="Pause Run Schedule",
    description="Pause a run schedule so it stops firing.",
)
async def pause_run_schedule(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: PauseRunScheduleRequest | None = None,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.update,
    )
    note = request.note if request else None
    return await run_schedules_use_case.pause_schedule(agent_id, schedule_id, note=note)


@router.post(
    "/name/{name}/resume",
    response_model=AgentRunScheduleResponse,
    summary="Resume Run Schedule By Name",
    description="Resume a paused run schedule by its active name.",
)
async def resume_run_schedule_by_name(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: ResumeRunScheduleRequest | None = None,
) -> AgentRunScheduleResponse:
    schedule_id = await _resolve_name_alias_and_check(
        agent_id,
        name,
        AuthorizedOperationType.update,
        run_schedules_use_case,
        authorization,
    )
    note = request.note if request else None
    return await run_schedules_use_case.resume_schedule(
        agent_id, schedule_id, note=note
    )


@router.post(
    "/{schedule_id}/resume",
    response_model=AgentRunScheduleResponse,
    summary="Resume Run Schedule",
    description="Resume a paused run schedule so it fires again.",
)
async def resume_run_schedule(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
    request: ResumeRunScheduleRequest | None = None,
) -> AgentRunScheduleResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.update,
    )
    note = request.note if request else None
    return await run_schedules_use_case.resume_schedule(
        agent_id, schedule_id, note=note
    )


@router.delete(
    "/name/{name}",
    response_model=DeleteResponse,
    summary="Delete Run Schedule By Name",
    description="Delete a run schedule by its active name.",
)
async def delete_run_schedule_by_name(
    agent_id: str,
    name: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> DeleteResponse:
    schedule_id = await _resolve_name_alias_and_check(
        agent_id,
        name,
        AuthorizedOperationType.delete,
        run_schedules_use_case,
        authorization,
    )
    deleted_schedule_id = await run_schedules_use_case.delete_schedule(
        agent_id, schedule_id
    )
    return DeleteResponse(
        id=deleted_schedule_id,
        message=f"Run schedule '{name}' deleted successfully",
    )


@router.delete(
    "/{schedule_id}",
    response_model=DeleteResponse,
    summary="Delete Run Schedule",
    description="Delete a run schedule permanently.",
)
async def delete_run_schedule(
    agent_id: str,
    schedule_id: str,
    run_schedules_use_case: DAgentRunSchedulesUseCase,
    authorization: DAuthorizationService,
) -> DeleteResponse:
    await _check_schedule_or_collapse_to_404(
        authorization,
        build_run_schedule_authz_selector(agent_id, schedule_id),
        AuthorizedOperationType.delete,
    )
    deleted_schedule_id = await run_schedules_use_case.delete_schedule(
        agent_id, schedule_id
    )
    return DeleteResponse(
        id=deleted_schedule_id,
        message=f"Run schedule '{schedule_id}' deleted successfully",
    )
