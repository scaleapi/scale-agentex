from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import Depends
from temporalio.client import ScheduleDescription

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.adapters.temporal.adapter_temporal import DTemporalAdapter, TemporalAdapter
from src.adapters.temporal.exceptions import TemporalScheduleNotFoundError
from src.api.schemas.agent_run_schedules import (
    AgentRunScheduleListResponse,
    AgentRunScheduleResponse,
    CreateAgentRunScheduleRequest,
    RunScheduleState,
    ScheduleCreatorPrincipal,
    ScheduleInitialInput,
    UpdateAgentRunScheduleRequest,
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
from src.domain.repositories.task_repository import DTaskRepository
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


def build_run_schedule_authz_selector(agent_id: str, schedule_id: str) -> str:
    """Authorization selector for a run schedule's ``schedule`` resource.

    Derivable from the (agent_id, schedule_id) path params so the CRUD endpoints
    can authorize without a prior DB lookup. The ``run-schedule::`` prefix
    namespaces the selector within the ``schedule`` resource type.
    """
    return f"run-schedule::{agent_id}::{schedule_id}"


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
        task_repository: DTaskRepository,
    ):
        self.temporal_adapter = temporal_adapter
        self.authorization_service = authorization_service
        self.schedule_repository = schedule_repository
        self.agent_repository = agent_repository
        self.task_repository = task_repository

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
        )

        try:
            created = await self.schedule_repository.create(entity)
        except DuplicateItemError as exc:
            raise ClientError(
                f"Run schedule '{request.name}' already exists for agent '{agent.id}'"
            ) from exc

        temporal_id = build_run_schedule_temporal_id(created.id)
        authz_selector = build_run_schedule_authz_selector(agent.id, created.id)
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
            # Temporal schedules append the nominal fire timestamp to this base
            # workflow id at execution time, so workflow.info().workflow_id is a
            # per-fire token even though the configured action id is stable.
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
        # Fetch without a DB limit so the authorization filter below runs against
        # the full set, then truncate to ``limit`` after filtering. Applying the
        # DB limit first would drop authorized schedules that sort beyond the
        # window before the auth filter ever sees them, silently hiding rows the
        # caller is entitled to. Safe at the expected low per-agent row count; if
        # schedules per agent ever grow large, push the authorized names into the
        # query instead.
        rows = await self.schedule_repository.list_by_agent_id(agent_id)

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
            if len(items) >= limit:
                break
            selector = build_run_schedule_authz_selector(agent_id, row.id)
            if authorized is not None and selector not in authorized:
                continue
            temporal_id = build_run_schedule_temporal_id(row.id)
            # Serve the list from Postgres only — no per-row Temporal describe.
            # Fanning out one RPC per row (up to the route's limit of 1000) makes
            # list latency scale with Temporal round-trips; live fields are
            # available on the single-schedule GET instead.
            items.append(
                await self._to_response(
                    row, agent=agent, temporal_id=temporal_id, include_live=False
                )
            )
        return AgentRunScheduleListResponse(run_schedules=items, total=len(items))

    async def get_schedule(
        self, agent_id: str, schedule_id: str
    ) -> AgentRunScheduleResponse:
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(
            row, agent=agent, temporal_id=build_run_schedule_temporal_id(row.id)
        )

    async def get_schedule_id_by_name(self, agent_id: str, name: str) -> str:
        row = await self.schedule_repository.get_by_agent_id_and_name(agent_id, name)
        if row is None:
            raise ItemDoesNotExist(
                f"Run schedule '{name}' for agent '{agent_id}' does not exist."
            )
        return row.id

    async def pause_schedule(
        self, agent_id: str, schedule_id: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self._set_paused(agent_id, schedule_id, paused=True, note=note)

    async def resume_schedule(
        self, agent_id: str, schedule_id: str, note: str | None = None
    ) -> AgentRunScheduleResponse:
        return await self._set_paused(agent_id, schedule_id, paused=False, note=note)

    async def delete_schedule(self, agent_id: str, schedule_id: str) -> str:
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        # Temporal is the recurring clock; delete it first so no further fires can
        # occur, then soft-delete the row and drop the auth entry. The Postgres row
        # is tombstoned (deleted_at set) rather than removed so the schedule remains
        # auditable.
        # A missing Temporal schedule is treated as success (the clock is already
        # gone) so a prior partial delete — Temporal removed but the row write
        # failed — can still be cleaned up through this path rather than stranded.
        try:
            await self.temporal_adapter.delete_schedule(temporal_id)
        except TemporalScheduleNotFoundError:
            logger.warning(
                "run_schedule_temporal_already_absent_on_delete",
                extra={"temporal_id": temporal_id, "schedule_id": row.id},
            )
        row.deleted_at = datetime.now(UTC)
        await self.schedule_repository.update(row)
        await self._deregister_schedule_from_auth(
            authz_selector=build_run_schedule_authz_selector(agent_id, row.id)
        )
        return row.id

    async def update_schedule(
        self, agent_id: str, schedule_id: str, request: UpdateAgentRunScheduleRequest
    ) -> AgentRunScheduleResponse:
        """Apply a partial update to a schedule's definition and Temporal spec.

        Only fields present in the request are changed. Setting one of
        cron_expression / interval_seconds clears the other; the merged result
        must still have exactly one cadence.
        """
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        provided = request.model_dump(exclude_unset=True)
        if "name" in provided and request.name is not None and request.name != row.name:
            existing = await self.schedule_repository.get_by_agent_id_and_name(
                agent_id, request.name
            )
            if existing is not None and existing.id != row.id:
                raise ClientError(
                    f"Run schedule '{request.name}' already exists for agent '{agent_id}'"
                )
            row.name = request.name
        if "description" in provided:
            row.description = request.description
        if "cron_expression" in provided:
            row.cron_expression = request.cron_expression
            if request.cron_expression is not None:
                row.interval_seconds = None
        if "interval_seconds" in provided:
            row.interval_seconds = request.interval_seconds
            if request.interval_seconds is not None:
                row.cron_expression = None
        if "timezone" in provided and request.timezone is not None:
            row.timezone = request.timezone
        if "start_at" in provided:
            row.start_at = request.start_at
        if "end_at" in provided:
            row.end_at = request.end_at
        if "paused" in provided and request.paused is not None:
            row.paused = request.paused
        if "task_params" in provided:
            row.task_params = request.task_params
        if "task_metadata" in provided:
            row.task_metadata = request.task_metadata
        if "initial_input" in provided and request.initial_input is not None:
            row.initial_input = request.initial_input.to_dict(mode="json")

        if not row.cron_expression and not row.interval_seconds:
            raise ClientError(
                "Schedule must have exactly one of cron_expression or interval_seconds"
            )
        if row.cron_expression and row.interval_seconds:
            raise ClientError(
                "Provide only one of cron_expression or interval_seconds, not both"
            )

        temporal_id = build_run_schedule_temporal_id(row.id)
        # Push the merged cadence/window/paused state to the Temporal clock BEFORE
        # committing the row. This closes the common divergence: a rejected spec
        # (invalid cron / timezone) or a transient Temporal error aborts the
        # update with nothing persisted. A residual window remains — if Temporal
        # accepts the update and the row write below then fails, the clock leads
        # the row — but there is no cross-store transaction, and the row stays the
        # declared source of truth, so any later successful update re-converges
        # them. (Create keeps the analogous invariant by rolling the row back on
        # failure; update has no in-place rollback, so it orders the writes
        # instead.) A missing schedule is logged rather than raised so the
        # persisted row stays authoritative (mirrors the describe/delete
        # tolerance) and the merged definition is still committed.
        try:
            await self.temporal_adapter.update_schedule(
                schedule_id=temporal_id,
                cron_expressions=(
                    [row.cron_expression] if row.cron_expression else None
                ),
                interval_seconds=row.interval_seconds,
                start_at=row.start_at,
                end_at=row.end_at,
                time_zone_name=row.timezone if row.cron_expression else None,
                paused=row.paused,
            )
        except TemporalScheduleNotFoundError:
            logger.warning(
                "run_schedule_temporal_missing_on_update",
                extra={"temporal_id": temporal_id, "schedule_id": row.id},
            )
        try:
            updated = await self.schedule_repository.update(row)
        except DuplicateItemError as exc:
            raise ClientError(
                f"Run schedule '{row.name}' already exists for agent '{agent_id}'"
            ) from exc
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(updated, agent=agent, temporal_id=temporal_id)

    async def trigger_schedule(
        self, agent_id: str, schedule_id: str
    ) -> AgentRunScheduleResponse:
        """Trigger an immediate, out-of-band fire of the schedule."""
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        triggered_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        # Schedule starts get a Temporal-generated timestamp suffix; direct manual
        # starts need their own uniqueness source, while keeping a parseable time.
        await self.temporal_adapter.start_workflow(
            workflow=SCHEDULED_AGENT_RUN_WORKFLOW_NAME,
            workflow_id=f"{temporal_id}-manual-{uuid4()}-{triggered_at}",
            args=[row.id, "manual"],
            task_queue=self._task_queue(),
        )
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(row, agent=agent, temporal_id=temporal_id)

    async def skip_schedule_action(
        self, agent_id: str, schedule_id: str, scheduled_time: datetime
    ) -> AgentRunScheduleResponse:
        """Skip a specific recurring fire."""
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        await self.temporal_adapter.skip_schedule_action(
            temporal_id, scheduled_time=scheduled_time
        )
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(row, agent=agent, temporal_id=temporal_id)

    async def unskip_schedule_action(
        self, agent_id: str, schedule_id: str, scheduled_time: datetime
    ) -> AgentRunScheduleResponse:
        """Remove a skipped recurring fire."""
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        await self.temporal_adapter.unskip_schedule_action(
            temporal_id, scheduled_time=scheduled_time
        )
        agent = await self.agent_repository.get(id=agent_id)
        return await self._to_response(row, agent=agent, temporal_id=temporal_id)

    # -- internals ---------------------------------------------------------

    async def _set_paused(
        self, agent_id: str, schedule_id: str, *, paused: bool, note: str | None
    ) -> AgentRunScheduleResponse:
        row = await self.schedule_repository.get_by_agent_id_and_id_or_raise(
            agent_id, schedule_id
        )
        temporal_id = build_run_schedule_temporal_id(row.id)
        # A missing Temporal schedule is logged rather than raised: the persisted
        # ``paused`` flag is authoritative and the activity honors it defensively,
        # so a missing clock can't strand the row in an un-toggleable state.
        try:
            if paused:
                await self.temporal_adapter.pause_schedule(temporal_id, note=note)
            else:
                await self.temporal_adapter.unpause_schedule(temporal_id, note=note)
        except TemporalScheduleNotFoundError:
            logger.warning(
                "run_schedule_temporal_missing_on_pause_toggle",
                extra={
                    "temporal_id": temporal_id,
                    "schedule_id": row.id,
                    "paused": paused,
                },
            )
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
        include_live: bool = True,
    ) -> AgentRunScheduleResponse:
        effective_method = infer_initial_input_method(agent.acp_type).value

        state = RunScheduleState.PAUSED if entity.paused else RunScheduleState.ACTIVE
        next_action_times: list[datetime] = []
        skipped_action_times: list[datetime] = []
        last_action_time: datetime | None = None
        num_actions_taken = 0
        num_tasks_created = (
            await self.task_repository.count_by_agent_id_and_task_metadata(
                agent_id=entity.agent_id,
                task_metadata={"schedule_id": entity.id},
            )
        )

        # Live Temporal fields are best-effort and opt-in. ``include_live=False``
        # (list path) skips the describe RPC entirely and serves state from the
        # persisted ``paused`` flag. When enabled (single GET), a describe failure
        # (e.g. right after creation, or a transient Temporal error) must not break
        # the response, which is fully serviceable from the persisted row.
        if include_live:
            try:
                description = await self.temporal_adapter.describe_schedule(temporal_id)
                live = self._extract_live_fields(description)
                state = live["state"]
                next_action_times = live["next_action_times"]
                skipped_action_times = live["skipped_action_times"]
                last_action_time = live["last_action_time"]
                num_actions_taken = live["num_actions_taken"]
            except Exception as exc:
                logger.warning(
                    "run_schedule_describe_failed",
                    extra={
                        "temporal_id": temporal_id,
                        "error_type": type(exc).__name__,
                    },
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
            skipped_action_times=skipped_action_times,
            last_action_time=last_action_time,
            num_actions_taken=num_actions_taken,
            num_tasks_created=num_tasks_created,
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
        skipped_action_times = TemporalAdapter.extract_one_off_skip_times(
            description, after=datetime.now(UTC)
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
            "skipped_action_times": skipped_action_times,
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
        schedule_resource = AgentexResource.schedule(authz_selector)
        await self.authorization_service.register_resource(
            resource=schedule_resource,
            parent=AgentexResource.agent(agent_id),
        )
        try:
            # Legacy SGP auth treats register_resource as a no-op. Keep the
            # Spark registration above for the future path, and write the legacy
            # grant so current list/check calls can see the schedule.
            await self.authorization_service.grant(schedule_resource)
        except Exception as grant_exc:
            logger.warning(
                "Auth grant failed for run schedule; compensating with deregister",
                extra={
                    "authz_selector": authz_selector,
                    "error_type": type(grant_exc).__name__,
                },
                exc_info=True,
            )
            try:
                await self.authorization_service.deregister_resource(
                    resource=schedule_resource,
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "Auth deregister failed after run schedule grant failure",
                    extra={
                        "authz_selector": authz_selector,
                        "error_type": type(cleanup_exc).__name__,
                    },
                    exc_info=True,
                )
            raise
        return True

    async def _deregister_schedule_from_auth(self, *, authz_selector: str) -> None:
        schedule_resource = AgentexResource.schedule(authz_selector)
        try:
            await self.authorization_service.revoke(resource=schedule_resource)
        except Exception as exc:
            logger.warning(
                "Auth revoke failed for run schedule; entry may be orphaned",
                extra={
                    "authz_selector": authz_selector,
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
        try:
            await self.authorization_service.deregister_resource(
                resource=schedule_resource
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
