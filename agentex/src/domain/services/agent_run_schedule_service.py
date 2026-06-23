from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import Depends
from temporalio.client import ScheduleDescription

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.adapters.temporal.adapter_temporal import DTemporalAdapter
from src.api.schemas.agent_run_schedules import (
    AgentRunScheduleListResponse,
    AgentRunScheduleResponse,
    CreateAgentRunScheduleRequest,
    RunScheduleState,
    ScheduleCreatorPrincipal,
    ScheduleInitialInput,
)
from src.api.schemas.authorization_types import AgentexResource
from src.domain.entities.agent_run_schedules import (
    AgentRunScheduleEntity,
    infer_initial_input_method,
)
from src.domain.entities.agents import AgentEntity
from src.domain.exceptions import ClientError
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.repositories.agent_run_schedule_repository import (
    DAgentRunScheduleRepository,
)
from src.domain.services.authorization_service import DAuthorizationService
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Temporal schedule id derived from the Postgres row id. The prefix namespaces
# these schedules within the shared Temporal namespace and keeps the id stable
# and small (the row id is the only thing the workflow needs).
RUN_SCHEDULE_TEMPORAL_ID_PREFIX = "agent-run-schedule"

# Registered (class) name of the workflow each fire starts. Referenced by name so
# the API/service layer doesn't import the Temporal workflow definition.
SCHEDULED_AGENT_RUN_WORKFLOW_NAME = "ScheduledAgentRunWorkflow"


def build_run_schedule_temporal_id(schedule_row_id: str) -> str:
    return f"{RUN_SCHEDULE_TEMPORAL_ID_PREFIX}:{schedule_row_id}"


def build_run_schedule_authz_selector(agent_id: str, name: str) -> str:
    """Authorization selector for a run schedule's ``schedule`` resource.

    Derivable from the (agent_id, name) path params so the CRUD endpoints can
    authorize without a prior DB lookup. The ``run-schedule::`` prefix namespaces
    the selector within the ``schedule`` resource type.
    """
    return f"run-schedule::{agent_id}::{name}"


class AgentRunScheduleService:
    """Manage Postgres-backed scheduled agent runs and their Temporal Schedules.

    The Postgres row is the source of truth for the schedule definition; the
    Temporal Schedule is only the recurring clock and is given nothing but the
    schedule row id as its workflow argument.
    """

    def __init__(
        self,
        temporal_adapter: DTemporalAdapter,
        authorization_service: DAuthorizationService,
        schedule_repository: DAgentRunScheduleRepository,
        agent_repository: DAgentRepository,
    ):
        self.temporal_adapter = temporal_adapter
        self.authorization_service = authorization_service
        self.schedule_repository = schedule_repository
        self.agent_repository = agent_repository

    async def create_schedule(
        self,
        agent: AgentEntity,
        request: CreateAgentRunScheduleRequest,
        creator_principal: dict[str, Any],
    ) -> AgentRunScheduleResponse:
        existing = await self.schedule_repository.get_by_agent_id_and_name(
            agent.id, request.name
        )
        if existing is not None:
            raise ClientError(
                f"Run schedule '{request.name}' already exists for agent '{agent.id}'"
            )

        entity = AgentRunScheduleEntity(
            id=orm_id(),
            agent_id=agent.id,
            name=request.name,
            description=request.description,
            cron_expression=request.cron_expression,
            interval_seconds=request.interval_seconds,
            timezone=request.timezone,
            start_at=request.start_at,
            end_at=request.end_at,
            paused=request.paused,
            creator_principal=creator_principal,
            task_params=request.task_params,
            task_metadata=request.task_metadata,
            initial_input=request.initial_input.to_dict(mode="json"),
            # Delivery method is inferred from the agent's ACP type at fire time.
            initial_input_method=None,
        )

        try:
            created = await self.schedule_repository.create(entity)
        except DuplicateItemError as exc:
            raise ClientError(
                f"Run schedule '{request.name}' already exists for agent '{agent.id}'"
            ) from exc

        temporal_id = build_run_schedule_temporal_id(created.id)
        authz_selector = build_run_schedule_authz_selector(agent.id, created.name)
        # Register (fail-closed, before the Temporal write) and create the schedule
        # under one rollback scope: if EITHER the auth registration or the Temporal
        # create fails, the persisted row is removed so a failed create leaves
        # nothing behind. Registration happens first so an auth failure aborts
        # before the Temporal write.
        registered = False
        try:
            registered = await self._register_schedule_in_auth(
                authz_selector=authz_selector, agent_id=agent.id
            )
            await self.temporal_adapter.create_schedule(
                schedule_id=temporal_id,
                workflow=SCHEDULED_AGENT_RUN_WORKFLOW_NAME,
                workflow_id=f"{temporal_id}-run",
                args=[created.id],
                task_queue=self._task_queue(),
                cron_expressions=(
                    [created.cron_expression] if created.cron_expression else None
                ),
                interval_seconds=created.interval_seconds,
                start_at=created.start_at,
                end_at=created.end_at,
                paused=created.paused,
                time_zone_name=created.timezone if created.cron_expression else None,
                overlap_policy="skip",
            )
        except Exception:
            if registered:
                await self._deregister_schedule_from_auth(authz_selector=authz_selector)
            await self._best_effort_delete_row(created.id)
            raise

        return await self._to_response(created, agent=agent, temporal_id=temporal_id)

    async def list_schedules(
        self,
        agent_id: str,
        authorized_schedule_ids: list[str] | None = None,
        limit: int = 100,
    ) -> AgentRunScheduleListResponse:
        rows = await self.schedule_repository.list_by_agent_id(agent_id, limit=limit)

        # Gate on ``is not None``: an empty list means the caller owns nothing and
        # everything is filtered out; None means authorization is bypassed.
        authorized = (
            set(authorized_schedule_ids)
            if authorized_schedule_ids is not None
            else None
        )
        agent = await self.agent_repository.get(id=agent_id)
        items: list[AgentRunScheduleResponse] = []
        for row in rows:
            selector = build_run_schedule_authz_selector(agent_id, row.name)
            if authorized is not None and selector not in authorized:
                continue
            temporal_id = build_run_schedule_temporal_id(row.id)
            items.append(
                await self._to_response(row, agent=agent, temporal_id=temporal_id)
            )
        return AgentRunScheduleListResponse(run_schedules=items, total=len(items))

    async def get_schedule(self, agent_id: str, name: str) -> AgentRunScheduleResponse:
        row = await self.schedule_repository.get_by_agent_id_and_name_or_raise(
            agent_id, name
        )
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(
            row, agent=agent, temporal_id=build_run_schedule_temporal_id(row.id)
        )

    async def pause_schedule(
        self, agent_id: str, name: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self._set_paused(agent_id, name, paused=True, note=note)

    async def resume_schedule(
        self, agent_id: str, name: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self._set_paused(agent_id, name, paused=False, note=note)

    async def delete_schedule(self, agent_id: str, name: str) -> str:
        row = await self.schedule_repository.get_by_agent_id_and_name_or_raise(
            agent_id, name
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        # Temporal is the recurring clock; delete it first so no further fires can
        # occur, then drop the row and the auth entry (both best-effort after).
        await self.temporal_adapter.delete_schedule(temporal_id)
        await self.schedule_repository.delete(id=row.id)
        await self._deregister_schedule_from_auth(
            authz_selector=build_run_schedule_authz_selector(agent_id, row.name)
        )
        return row.id

    # -- internals ---------------------------------------------------------

    async def _set_paused(
        self, agent_id: str, name: str, *, paused: bool, note: str | None
    ) -> AgentRunScheduleResponse:
        row = await self.schedule_repository.get_by_agent_id_and_name_or_raise(
            agent_id, name
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        if paused:
            await self.temporal_adapter.pause_schedule(temporal_id, note=note)
        else:
            await self.temporal_adapter.unpause_schedule(temporal_id, note=note)
        row.paused = paused
        updated = await self.schedule_repository.update(row)
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(updated, agent=agent, temporal_id=temporal_id)

    def _task_queue(self) -> str:
        # Local import avoids a circular import (run_worker imports the factory,
        # which would otherwise transitively import this service).
        from src.temporal.run_worker import AGENTEX_SERVER_TASK_QUEUE

        return AGENTEX_SERVER_TASK_QUEUE

    async def _to_response(
        self,
        entity: AgentRunScheduleEntity,
        agent: AgentEntity,
        temporal_id: str,
    ) -> AgentRunScheduleResponse:
        effective_method = (
            entity.initial_input_method
            or infer_initial_input_method(agent.acp_type).value
        )

        state = RunScheduleState.PAUSED if entity.paused else RunScheduleState.ACTIVE
        next_action_times: list[datetime] = []
        last_action_time: datetime | None = None
        num_actions_taken = 0

        # Live Temporal fields are best-effort: a describe failure (e.g. right
        # after creation, or a transient Temporal error) must not break the
        # response, which is fully serviceable from the persisted row.
        try:
            description = await self.temporal_adapter.describe_schedule(temporal_id)
            live = self._extract_live_fields(description)
            state = live["state"]
            next_action_times = live["next_action_times"]
            last_action_time = live["last_action_time"]
            num_actions_taken = live["num_actions_taken"]
        except Exception as exc:
            logger.warning(
                "run_schedule_describe_failed",
                extra={"temporal_id": temporal_id, "error_type": type(exc).__name__},
            )

        return AgentRunScheduleResponse(
            id=entity.id,
            agent_id=entity.agent_id,
            name=entity.name,
            description=entity.description,
            cron_expression=entity.cron_expression,
            interval_seconds=entity.interval_seconds,
            timezone=entity.timezone,
            start_at=entity.start_at,
            end_at=entity.end_at,
            paused=entity.paused,
            task_params=entity.task_params,
            task_metadata=entity.task_metadata,
            initial_input=ScheduleInitialInput.model_validate(entity.initial_input),
            initial_input_method=effective_method,
            creator_principal=ScheduleCreatorPrincipal.model_validate(
                entity.creator_principal
            ),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            state=state,
            next_action_times=next_action_times,
            last_action_time=last_action_time,
            num_actions_taken=num_actions_taken,
        )

    @staticmethod
    def _extract_live_fields(description: ScheduleDescription) -> dict[str, Any]:
        state = RunScheduleState.ACTIVE
        if description.schedule.state and description.schedule.state.paused:
            state = RunScheduleState.PAUSED

        info = description.info
        next_action_times = (
            list(info.next_action_times) if info.next_action_times else []
        )
        last_action_time: datetime | None = None
        if getattr(info, "recent_actions", None):
            last_action = info.recent_actions[-1]
            last_action_time = getattr(last_action, "started_at", None) or getattr(
                last_action, "scheduled_at", None
            )
        num_actions_taken = (
            cast(int, info.num_actions) if hasattr(info, "num_actions") else 0
        )
        return {
            "state": state,
            "next_action_times": next_action_times,
            "last_action_time": last_action_time,
            "num_actions_taken": num_actions_taken,
        }

    async def _register_schedule_in_auth(
        self, *, authz_selector: str, agent_id: str
    ) -> bool:
        """Register the schedule under its parent agent so permissions cascade.

        Returns True when registered, or False when no creator identity is
        resolvable (mirrors ScheduleService: registration is skipped under authz
        bypass / when no principal is present).
        """
        principal_context = self.authorization_service.principal_context
        if isinstance(principal_context, dict):
            user_id = principal_context.get("user_id")
            service_account_id = principal_context.get("service_account_id")
        else:
            user_id = getattr(principal_context, "user_id", None)
            service_account_id = getattr(principal_context, "service_account_id", None)
        if user_id is None and service_account_id is None:
            logger.warning(
                "Skipping auth registration for run schedule: no creator resolvable",
                extra={"authz_selector": authz_selector, "agent_id": agent_id},
            )
            return False
        await self.authorization_service.register_resource(
            resource=AgentexResource.schedule(authz_selector),
            parent=AgentexResource.agent(agent_id),
        )
        return True

    async def _deregister_schedule_from_auth(self, *, authz_selector: str) -> None:
        try:
            await self.authorization_service.deregister_resource(
                resource=AgentexResource.schedule(authz_selector),
            )
        except Exception as exc:
            logger.warning(
                "Auth deregister failed for run schedule; entry may be orphaned",
                extra={
                    "authz_selector": authz_selector,
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )

    async def _best_effort_delete_row(self, schedule_id: str) -> None:
        try:
            await self.schedule_repository.delete(id=schedule_id)
        except ItemDoesNotExist:
            pass
        except Exception:
            logger.exception(
                "Failed to roll back run schedule row after Temporal create failure",
                extra={"schedule_id": schedule_id},
            )


DAgentRunScheduleService = Annotated[
    AgentRunScheduleService, Depends(AgentRunScheduleService)
]
