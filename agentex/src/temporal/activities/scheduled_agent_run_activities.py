"""
Temporal activity for scheduled agent runs.

``launch_scheduled_agent_run`` is the single activity each scheduled fire runs.
It loads the persisted schedule, creates a fresh Agentex task with a deterministic
name, and delivers the configured initial input through the same path a manual
agent run uses — ``task/create`` then ``event/send`` (async / agentic agents) or
``message/send`` (sync agents) — attributed to the schedule's stored creator
principal.

Correctness:
- Deterministic task name ``scheduled-run:{schedule_id}:{fire_id}`` makes
  ``task/create`` get-or-create, so an activity retry returns the same task
  instead of duplicating it.
- A ``scheduled_input_delivered`` marker on the task metadata guards against
  re-delivering the initial input when the activity retries after a prior
  successful delivery.

Boundary types are JSON-native (the backend data converter does not serialize
Pydantic models), so args and the return value are plain str / dict.
"""

import re
from datetime import UTC, datetime
from typing import Any

from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.config.dependencies import GlobalDependencies
from src.domain.entities.agent_run_schedules import (
    InitialInputMethod,
    infer_initial_input_method,
)
from src.domain.entities.agents import AgentStatus
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    CreateTaskRequestEntity,
    SendEventRequestEntity,
    SendMessageRequestEntity,
)
from src.domain.entities.task_messages import (
    MessageAuthor,
    TaskMessageContentEntity,
    TextContentEntity,
)
from src.domain.repositories.agent_run_schedule_repository import (
    AgentRunScheduleRepository,
)
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase
from src.temporal.scheduled_agent_run_factory import build_acp_use_case_for_principal
from src.utils.logging import make_logger
from temporalio import activity

logger = make_logger(__name__)

LAUNCH_SCHEDULED_AGENT_RUN_ACTIVITY = "launch_scheduled_agent_run_activity"

_INPUT_DELIVERED_MARKER = "scheduled_input_delivered"

# Temporal suffixes a scheduled workflow id with the nominal fire time
# (e.g. ``...-run-2026-06-23T15:19:00Z``). Matching the trailing ISO-8601 lets
# the display label use the *scheduled* time, which is stable across activity
# retries, rather than wall-clock now() (which drifts on a delayed retry).
_NOMINAL_FIRE_TIME_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)$"
)


def _format_fire_time(fire_id: str) -> str:
    """Format the schedule's nominal fire time for the task display name.

    Falls back to the current time when ``fire_id`` carries no recognizable
    timestamp suffix (e.g. a manually triggered fire).
    """
    fire_time = _extract_fire_time(fire_id)
    if fire_time is not None:
        parsed = datetime.fromisoformat(fire_time.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _extract_fire_time(fire_id: str) -> str | None:
    """Extract the occurrence time encoded in a schedule/manual fire id."""
    match = _NOMINAL_FIRE_TIME_RE.search(fire_id)
    if match:
        try:
            parsed = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return None


def _build_initial_content(initial_input: dict[str, Any]) -> TaskMessageContentEntity:
    """Build the message content delivered as the scheduled task's first input.

    Only text input is supported (enforced by ``ScheduleInitialInput.type``).
    """
    author = initial_input.get("author", MessageAuthor.USER.value)
    if not isinstance(author, MessageAuthor):
        author = MessageAuthor(author)
    return TextContentEntity(
        author=author,
        content=initial_input.get("content", ""),
    )


async def _authorize_or_skip(
    authorization_service: Any,
    checks: list[tuple[Any, Any]],
    *,
    schedule_id: str,
    task_id: str | None = None,
) -> dict[str, Any] | None:
    """Run fire-time AuthZ checks under the stored creator principal.

    Returns ``None`` when every check passes (or authz is bypassed). On a
    permanent ``AuthorizationError`` (403) it returns a
    ``skipped`` / ``permission_denied`` outcome so a revoked principal stops
    future fires; transient authz errors propagate so Temporal retries.
    """
    for resource, operation in checks:
        try:
            await authorization_service.check(resource=resource, operation=operation)
        except AuthorizationError as exc:
            logger.warning(
                "scheduled_run_permission_denied",
                extra={
                    "schedule_id": schedule_id,
                    "resource": f"{resource.type}:{resource.selector}",
                    "operation": str(operation),
                },
            )
            outcome: dict[str, Any] = {
                "status": "skipped",
                "reason": "permission_denied",
                "schedule_id": schedule_id,
                "detail": str(exc),
            }
            if task_id is not None:
                outcome["task_id"] = task_id
            return outcome
    return None


class ScheduledAgentRunActivities:
    def __init__(
        self,
        global_dependencies: GlobalDependencies,
        schedule_repository: AgentRunScheduleRepository,
    ):
        self.global_dependencies = global_dependencies
        self.schedule_repository = schedule_repository

    @activity.defn(name=LAUNCH_SCHEDULED_AGENT_RUN_ACTIVITY)
    async def launch_scheduled_agent_run(
        self, schedule_id: str, fire_id: str, trigger_type: str = "scheduled"
    ) -> dict[str, Any]:
        """Create a task for the scheduled fire and deliver its initial input.

        Args:
            schedule_id: The persisted ``agent_run_schedules`` row id.
            fire_id: A token unique to this scheduled fire (the workflow id,
                which Temporal makes unique per fire and stable across activity
                retries within the same execution). Used to build the
                deterministic, idempotent task name.
            trigger_type: ``scheduled`` for cadence fires, ``manual`` for runs
                started by the trigger endpoint.

        Returns:
            A JSON-native dict describing the outcome (``launched`` / ``skipped``).
        """
        try:
            schedule = await self.schedule_repository.get(id=schedule_id)
        except ItemDoesNotExist:
            logger.warning(
                "scheduled_run_schedule_not_found",
                extra={"schedule_id": schedule_id, "fire_id": fire_id},
            )
            return {
                "status": "skipped",
                "reason": "schedule_not_found",
                "schedule_id": schedule_id,
            }

        if schedule.deleted_at is not None:
            return {
                "status": "skipped",
                "reason": "schedule_deleted",
                "schedule_id": schedule_id,
            }

        if schedule.paused and trigger_type != "manual":
            # Temporal pauses the schedule too, but a manual trigger can still
            # fire a paused schedule. Honor the stored paused state defensively
            # only for cadence-driven fires; explicit out-of-band manual triggers
            # bypass it so an operator can run a paused schedule on demand.
            return {
                "status": "skipped",
                "reason": "schedule_paused",
                "schedule_id": schedule_id,
            }

        use_case: AgentsACPUseCase = build_acp_use_case_for_principal(
            self.global_dependencies, schedule.creator_principal
        )

        agent = await use_case.agent_repository.get(id=schedule.agent_id)
        if agent.status == AgentStatus.DELETED:
            return {
                "status": "skipped",
                "reason": "agent_deleted",
                "schedule_id": schedule_id,
            }

        method = infer_initial_input_method(agent.acp_type).value

        # Re-check the stored creator principal's permission at fire time, mirroring
        # the JSON-RPC route's authorization order: agent.execute (the RPC endpoint
        # gate) then task.create (re-checks the creator's permission at fire time). A revoked
        # creator stops future fires instead of running under stale ownership.
        # AuthorizationError (403) is a permanent denial → skip cleanly; transient
        # authz errors propagate so Temporal retries. Under authz bypass (local /
        # disabled) these are no-ops.
        denied = await _authorize_or_skip(
            use_case.authorization_service,
            [
                (
                    AgentexResource.agent(schedule.agent_id),
                    AuthorizedOperationType.execute,
                ),
                (AgentexResource.task("*"), AuthorizedOperationType.create),
            ],
            schedule_id=schedule_id,
        )
        if denied is not None:
            return denied

        task_name = f"scheduled-run:{schedule_id}:{fire_id}"
        # Human-friendly label the UI renders for the task (it reads
        # task_metadata.display_name, never the deterministic `name` above).
        # Templated per fire so runs are distinguishable; placed first so a
        # caller-supplied display_name in schedule.task_metadata overrides it.
        display_fire_time = _format_fire_time(fire_id)
        task_metadata = {
            "display_name": f"Scheduled Message: {schedule.name} · {display_fire_time}",
            **(schedule.task_metadata or {}),
            "schedule_id": schedule_id,
            "scheduled_fire_id": fire_id,
            "trigger_type": trigger_type,
        }
        # `fire_time` is the run occurrence time: nominal scheduled time for
        # schedule-fired runs, and actual trigger time for manual runs. Store it
        # separately so product/UI code does not parse `scheduled_fire_id`.
        fire_time = _extract_fire_time(fire_id)
        if fire_time is not None:
            task_metadata["fire_time"] = fire_time

        # task/create — get-or-create by deterministic name, so a retry returns
        # the same task. For async / agentic agents this also forwards the task
        # to the ACP server; for sync agents it only persists the row.
        task = await use_case.handle_rpc_request(
            method=AgentRPCMethod.TASK_CREATE,
            params=CreateTaskRequestEntity(
                name=task_name,
                params=schedule.task_params,
                task_metadata=task_metadata,
            ),
            agent_id=schedule.agent_id,
        )

        # Duplicate-input guard: if this fire's task already carries the delivered
        # marker, a prior attempt already delivered the initial input.
        if task.task_metadata and task.task_metadata.get(_INPUT_DELIVERED_MARKER):
            return {
                "status": "skipped",
                "reason": "input_already_delivered",
                "task_id": task.id,
                "schedule_id": schedule_id,
            }

        # Mirror the route's per-method gate for event/send & message/send:
        # update permission on the task before delivering the initial input.
        denied = await _authorize_or_skip(
            use_case.authorization_service,
            [(AgentexResource.task(task.id), AuthorizedOperationType.update)],
            schedule_id=schedule_id,
            task_id=task.id,
        )
        if denied is not None:
            return denied

        content = _build_initial_content(schedule.initial_input)
        if method == InitialInputMethod.MESSAGE_SEND.value:
            await use_case.handle_rpc_request(
                method=AgentRPCMethod.MESSAGE_SEND,
                params=SendMessageRequestEntity(
                    task_name=task_name, content=content, stream=False
                ),
                agent_id=schedule.agent_id,
            )
        else:
            await use_case.handle_rpc_request(
                method=AgentRPCMethod.EVENT_SEND,
                params=SendEventRequestEntity(task_name=task_name, content=content),
                agent_id=schedule.agent_id,
            )

        # Best-effort delivered marker, written only AFTER delivery succeeds, so
        # scheduled delivery is at-least-once by design: a crash after send but
        # before this write makes a retry re-deliver (deterministic task naming
        # still prevents duplicate tasks). Marker-after is deliberate — claiming
        # before send would instead risk a silent missed delivery. A delivery-level
        # idempotency_key in event/send & message/send is the post-v1 fix.
        task.task_metadata = {
            **(task.task_metadata or {}),
            _INPUT_DELIVERED_MARKER: True,
        }
        await use_case.task_service.update_task(task)

        logger.info(
            "scheduled_run_launched",
            extra={
                "schedule_id": schedule_id,
                "task_id": task.id,
                "trigger_type": trigger_type,
                "method": method,
            },
        )
        return {
            "status": "launched",
            "task_id": task.id,
            "schedule_id": schedule_id,
            "trigger_type": trigger_type,
            "method": method,
        }
