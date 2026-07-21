import asyncio
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.adapters.temporal.exceptions import TemporalScheduleNotFoundError
from src.api.schemas.agent_run_schedules import (
    CreateAgentRunScheduleRequest,
    RunScheduleState,
    ScheduleInitialInput,
    SkipRunScheduleRequest,
    UnskipRunScheduleRequest,
    UpdateAgentRunScheduleRequest,
)
from src.api.schemas.authorization_types import AgentexResource
from src.domain.entities.agent_run_schedules import AgentRunScheduleEntity
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.exceptions import ClientError
from src.domain.services.agent_run_schedule_service import (
    AgentRunScheduleService,
    build_run_schedule_authz_selector,
    build_run_schedule_temporal_id,
)


@pytest.fixture
def agent():
    return AgentEntity(
        id="agent-123",
        name="test-agent",
        description="A test agent",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://acp.example.com",
    )


@pytest.fixture
def service():
    temporal_adapter = AsyncMock()
    # describe_schedule failing keeps _to_response on the persisted-row path.
    temporal_adapter.describe_schedule.side_effect = RuntimeError("not found yet")
    authorization_service = AsyncMock()
    type(authorization_service).principal_context = PropertyMock(
        return_value={"user_id": "u1", "account_id": "a1"}
    )
    schedule_repository = AsyncMock()
    agent_repository = AsyncMock()
    return AgentRunScheduleService(
        temporal_adapter=temporal_adapter,
        authorization_service=authorization_service,
        schedule_repository=schedule_repository,
        agent_repository=agent_repository,
    )


def _request(**overrides) -> CreateAgentRunScheduleRequest:
    payload: dict = {
        "name": "daily-summary",
        "cron_expression": "0 17 * * MON-FRI",
        "timezone": "America/New_York",
        "initial_input": ScheduleInitialInput(content="hello"),
    }
    payload.update(overrides)
    return CreateAgentRunScheduleRequest(**payload)


def _persisted(agent_id: str, request: CreateAgentRunScheduleRequest):
    return AgentRunScheduleEntity(
        id=str(uuid4()),
        agent_id=agent_id,
        name=request.name,
        cron_expression=request.cron_expression,
        interval_seconds=request.interval_seconds,
        timezone=request.timezone,
        paused=request.paused,
        creator_principal={"user_id": "u1", "account_id": "a1"},
        task_params=request.task_params,
        task_metadata=request.task_metadata,
        initial_input=request.initial_input.to_dict(mode="json"),
    )


class TestRunScheduleIdHelpers:
    def test_temporal_id_prefix(self):
        assert build_run_schedule_temporal_id("row-1") == "agent-run-schedule:row-1"

    def test_authz_selector_distinct_from_bare_schedule(self):
        # Bare schedules key the shared `schedule` resource as `{agent}--{name}`;
        # run schedules must not collide with that namespace.
        selector = build_run_schedule_authz_selector("agent-123", "schedule-456")
        assert selector == "run-schedule::agent-123::schedule-456"
        assert selector != "agent-123--daily-summary"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceCreate:
    async def test_create_persists_and_schedules(self, service, agent):
        request = _request()
        persisted = _persisted(agent.id, request)
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.create.return_value = persisted

        response = await service.create_schedule(agent, request, {"user_id": "u1"})

        # Temporal schedule points at the run workflow with only the row id as arg,
        # the server task queue, and the cron timezone passed through.
        create_kwargs = service.temporal_adapter.create_schedule.call_args.kwargs
        assert create_kwargs["workflow"] == "ScheduledAgentRunWorkflow"
        assert create_kwargs["args"] == [persisted.id]
        assert create_kwargs["schedule_id"] == build_run_schedule_temporal_id(
            persisted.id
        )
        assert create_kwargs["time_zone_name"] == "America/New_York"

        # Ownership is written to both auth paths before the Temporal write:
        # Spark resource registration for the future path, and a legacy grant
        # for current SGP list/check behavior.
        authz_selector = build_run_schedule_authz_selector(agent.id, persisted.id)
        schedule_resource = AgentexResource.schedule(authz_selector)
        service.authorization_service.register_resource.assert_called_once_with(
            resource=schedule_resource,
            parent=AgentexResource.agent(agent.id),
        )
        service.authorization_service.grant.assert_called_once_with(schedule_resource)

        assert response.name == "daily-summary"
        assert response.initial_input_method == "event/send"  # async agent
        assert response.state == RunScheduleState.ACTIVE
        assert response.initial_input.content == "hello"

    async def test_create_rejects_duplicate_name(self, service, agent):
        request = _request()
        service.schedule_repository.get_by_agent_id_and_name.return_value = _persisted(
            agent.id, request
        )

        with pytest.raises(ClientError):
            await service.create_schedule(agent, request, {"user_id": "u1"})

        service.temporal_adapter.create_schedule.assert_not_called()

    async def test_create_rolls_back_row_on_temporal_failure(self, service, agent):
        request = _request()
        persisted = _persisted(agent.id, request)
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.create.return_value = persisted
        service.temporal_adapter.create_schedule.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await service.create_schedule(agent, request, {"user_id": "u1"})

        # The orphaned row and both auth entries are compensated.
        authz_selector = build_run_schedule_authz_selector(agent.id, persisted.id)
        schedule_resource = AgentexResource.schedule(authz_selector)
        service.schedule_repository.delete.assert_called_once_with(id=persisted.id)
        service.authorization_service.revoke.assert_called_once_with(
            resource=schedule_resource
        )
        service.authorization_service.deregister_resource.assert_called_once()

    async def test_create_rolls_back_row_on_auth_registration_failure(
        self, service, agent
    ):
        request = _request()
        persisted = _persisted(agent.id, request)
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.create.return_value = persisted
        service.authorization_service.register_resource.side_effect = RuntimeError(
            "authz down"
        )

        with pytest.raises(RuntimeError):
            await service.create_schedule(agent, request, {"user_id": "u1"})

        # Auth registration failing must still roll back the persisted row, and
        # must not create a Temporal schedule.
        service.schedule_repository.delete.assert_called_once_with(id=persisted.id)
        service.temporal_adapter.create_schedule.assert_not_called()
        service.authorization_service.grant.assert_not_called()

    async def test_create_compensates_register_when_grant_fails(self, service, agent):
        request = _request()
        persisted = _persisted(agent.id, request)
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.create.return_value = persisted
        service.authorization_service.grant.side_effect = RuntimeError("authz down")

        with pytest.raises(RuntimeError):
            await service.create_schedule(agent, request, {"user_id": "u1"})

        # The Spark registration is compensated, the row is removed, and the
        # Temporal clock is never created if the legacy grant cannot be written.
        service.authorization_service.register_resource.assert_called_once()
        service.authorization_service.deregister_resource.assert_called_once()
        service.authorization_service.revoke.assert_not_called()
        service.schedule_repository.delete.assert_called_once_with(id=persisted.id)
        service.temporal_adapter.create_schedule.assert_not_called()

    async def test_create_skips_auth_when_no_creator(self, service, agent):
        type(service.authorization_service).principal_context = PropertyMock(
            return_value={}
        )
        request = _request()
        persisted = _persisted(agent.id, request)
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.create.return_value = persisted

        await service.create_schedule(agent, request, {})

        service.authorization_service.register_resource.assert_not_called()
        service.authorization_service.grant.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceList:
    async def test_list_filters_by_authorized_selectors(self, service, agent):
        req_a = _request(name="sched-a")
        req_b = _request(name="sched-b")
        rows = [_persisted(agent.id, req_a), _persisted(agent.id, req_b)]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        # Authorize only sched-a's selector.
        authorized = [build_run_schedule_authz_selector(agent.id, rows[0].id)]
        result = await service.list_schedules(
            agent.id, authorized_schedule_ids=authorized
        )

        assert result.total == 1
        assert result.run_schedules[0].name == "sched-a"

    async def test_list_filters_before_applying_limit(self, service, agent):
        # The auth filter must run before the limit is applied: an authorized
        # schedule that sorts beyond the limit window must still be returned, not
        # silently dropped by a DB-level limit applied before filtering.
        rows = [
            _persisted(agent.id, _request(name="other-a")),
            _persisted(agent.id, _request(name="other-b")),
            _persisted(agent.id, _request(name="mine")),
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        authorized = [build_run_schedule_authz_selector(agent.id, rows[2].id)]
        result = await service.list_schedules(
            agent.id, authorized_schedule_ids=authorized, limit=1
        )

        # The owned schedule is returned even though it sorts last and limit=1.
        assert result.total == 1
        assert result.run_schedules[0].name == "mine"
        # The query is no longer pre-truncated by limit (filtering happens first).
        _, kwargs = service.schedule_repository.list_by_agent_id.call_args
        assert kwargs.get("limit") is None

    async def test_list_none_authorized_means_bypass(self, service, agent):
        rows = [_persisted(agent.id, _request(name="sched-a"))]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        result = await service.list_schedules(agent.id, authorized_schedule_ids=None)

        assert result.total == 1

    async def test_list_does_not_fan_out_to_temporal(self, service, agent):
        # The list path must not issue a describe RPC per row (would scale list
        # latency with the number of schedules) unless explicitly requested.
        rows = [
            _persisted(agent.id, _request(name="sched-a")),
            _persisted(agent.id, _request(name="sched-b")),
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        await service.list_schedules(agent.id, authorized_schedule_ids=None)

        service.temporal_adapter.describe_schedule.assert_not_called()

    async def test_list_can_include_live_temporal_fields(self, service, agent):
        rows = [
            _persisted(agent.id, _request(name="sched-a")),
            _persisted(agent.id, _request(name="sched-b")),
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        result = await service.list_schedules(
            agent.id,
            authorized_schedule_ids=None,
            include_live=True,
        )

        assert result.total == 2
        assert all(
            schedule.live_data_available is False for schedule in result.run_schedules
        )
        assert service.temporal_adapter.describe_schedule.await_count == 2
        service.temporal_adapter.describe_schedule.assert_any_await(
            build_run_schedule_temporal_id(rows[0].id)
        )
        service.temporal_adapter.describe_schedule.assert_any_await(
            build_run_schedule_temporal_id(rows[1].id)
        )

    async def test_live_enrichment_uses_bounded_concurrency(self, service, agent):
        rows = [
            _persisted(agent.id, _request(name=f"sched-{index}")) for index in range(12)
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent
        active_calls = 0
        max_active_calls = 0

        async def describe_with_delay(_schedule_id):
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            await asyncio.sleep(0.01)
            active_calls -= 1
            raise RuntimeError("not found yet")

        service.temporal_adapter.describe_schedule.side_effect = describe_with_delay

        result = await service.list_schedules(
            agent.id,
            authorized_schedule_ids=None,
            include_live=True,
        )

        assert result.total == 12
        assert 1 < max_active_calls <= 10

    async def test_live_enrichment_caps_describe_fan_out(
        self, service, agent, monkeypatch
    ):
        # Rows beyond the fan-out ceiling are served DB-only (no describe RPC) so a
        # large ``limit`` can't turn one list request into unbounded Temporal calls.
        monkeypatch.setattr(
            "src.domain.services.agent_run_schedule_service.MAX_LIVE_ENRICHMENT_ROWS",
            2,
        )
        rows = [
            _persisted(agent.id, _request(name=f"sched-{index}")) for index in range(5)
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        result = await service.list_schedules(
            agent.id,
            authorized_schedule_ids=None,
            include_live=True,
        )

        # Every requested row is still returned, in order.
        assert result.total == 5
        # Only the first two rows triggered a describe; the rest are unknown (None),
        # not a false ``live_data_available=False``.
        assert service.temporal_adapter.describe_schedule.await_count == 2
        live_flags = [schedule.live_data_available for schedule in result.run_schedules]
        assert live_flags == [False, False, None, None, None]

    async def test_live_enrichment_waits_for_all_rows_before_raising(
        self, service, agent
    ):
        rows = [
            _persisted(agent.id, _request(name="bad")),
            _persisted(agent.id, _request(name="slow")),
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent
        completed_rows: list[str] = []

        async def convert_row(row, **_kwargs):
            if row.name == "slow":
                await asyncio.sleep(0.01)
            completed_rows.append(row.name)
            if row.name == "bad":
                raise ValueError("invalid stored schedule")
            return MagicMock()

        service._to_response = AsyncMock(side_effect=convert_row)

        with pytest.raises(ValueError, match="invalid stored schedule"):
            await service.list_schedules(
                agent.id,
                authorized_schedule_ids=None,
                include_live=True,
            )

        assert completed_rows == ["bad", "slow"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceNameLookup:
    async def test_get_schedule_id_by_name_returns_active_row_id(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_name.return_value = row

        result = await service.get_schedule_id_by_name(agent.id, row.name)

        assert result == row.id
        service.schedule_repository.get_by_agent_id_and_name.assert_awaited_once_with(
            agent.id, row.name
        )

    async def test_get_schedule_id_by_name_raises_when_absent(self, service, agent):
        service.schedule_repository.get_by_agent_id_and_name.return_value = None

        with pytest.raises(ItemDoesNotExist):
            await service.get_schedule_id_by_name(agent.id, "missing")


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceDelete:
    async def test_delete_tolerates_missing_temporal_schedule(self, service, agent):
        # Delete soft-deletes (tombstones) the row for audit rather than removing
        # it, and tolerates a missing Temporal schedule: a prior partial delete
        # (Temporal gone, row survived) must still be cleanable, treating a
        # missing clock as success.
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.temporal_adapter.delete_schedule.side_effect = (
            TemporalScheduleNotFoundError(message="gone", detail="gone")
        )

        result = await service.delete_schedule(agent.id, row.id)

        assert result == row.id
        # Soft delete: the row is tombstoned via update, not hard-removed.
        service.schedule_repository.delete.assert_not_called()
        service.schedule_repository.update.assert_called_once()
        tombstoned = service.schedule_repository.update.call_args.args[0]
        assert tombstoned.deleted_at is not None
        authz_selector = build_run_schedule_authz_selector(agent.id, row.id)
        schedule_resource = AgentexResource.schedule(authz_selector)
        service.authorization_service.revoke.assert_called_once_with(
            resource=schedule_resource
        )
        service.authorization_service.deregister_resource.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServicePauseResume:
    async def test_pause_tolerates_missing_temporal_schedule(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent
        service.temporal_adapter.pause_schedule.side_effect = (
            TemporalScheduleNotFoundError(message="gone", detail="gone")
        )

        response = await service.pause_schedule(agent.id, row.id)

        # The persisted paused flag is still flipped even though the clock is gone.
        assert row.paused is True
        assert response.paused is True
        service.schedule_repository.update.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceUpdate:
    async def test_update_swaps_cron_for_interval(self, service, agent):
        row = _persisted(agent.id, _request())  # cron-based
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent

        await service.update_schedule(
            agent.id, row.id, UpdateAgentRunScheduleRequest(interval_seconds=120)
        )

        # Setting interval clears cron, and the new cadence is pushed to Temporal.
        assert row.cron_expression is None
        assert row.interval_seconds == 120
        update_kwargs = service.temporal_adapter.update_schedule.call_args.kwargs
        assert update_kwargs["interval_seconds"] == 120
        assert update_kwargs["cron_expressions"] is None

    async def test_update_rejects_clearing_all_cadences(self, service, agent):
        row = _persisted(agent.id, _request())  # cron-based, no interval
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row

        # Explicitly nulling cron without supplying an interval leaves no cadence.
        with pytest.raises(ClientError):
            await service.update_schedule(
                agent.id, row.id, UpdateAgentRunScheduleRequest(cron_expression=None)
            )

        service.temporal_adapter.update_schedule.assert_not_called()

    async def test_update_tolerates_missing_temporal_schedule(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent
        service.temporal_adapter.update_schedule.side_effect = (
            TemporalScheduleNotFoundError(message="gone", detail="gone")
        )

        response = await service.update_schedule(
            agent.id, row.id, UpdateAgentRunScheduleRequest(description="new")
        )

        assert response.description == "new"

    async def test_update_does_not_commit_row_on_temporal_failure(self, service, agent):
        # A non-NotFound Temporal failure (rejected cron/timezone or a transient
        # outage) must abort before the row is persisted, so the DB can never
        # diverge from the clock. Unlike NotFound, this error propagates.
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.temporal_adapter.update_schedule.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await service.update_schedule(
                agent.id, row.id, UpdateAgentRunScheduleRequest(description="new")
            )

        service.schedule_repository.update.assert_not_called()

    async def test_update_allows_name_change(self, service, agent):
        row = _persisted(agent.id, _request(name="old-name"))
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent

        response = await service.update_schedule(
            agent.id, row.id, UpdateAgentRunScheduleRequest(name="new-name")
        )

        assert row.name == "new-name"
        assert response.name == "new-name"
        service.schedule_repository.get_by_agent_id_and_name.assert_awaited_once_with(
            agent.id, "new-name"
        )

    async def test_update_rejects_duplicate_active_name(self, service, agent):
        row = _persisted(agent.id, _request(name="old-name"))
        duplicate = _persisted(agent.id, _request(name="new-name"))
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.get_by_agent_id_and_name.return_value = duplicate

        with pytest.raises(ClientError):
            await service.update_schedule(
                agent.id, row.id, UpdateAgentRunScheduleRequest(name="new-name")
            )

        service.temporal_adapter.update_schedule.assert_not_called()
        service.schedule_repository.update.assert_not_called()

    async def test_update_converts_duplicate_index_error(self, service, agent):
        row = _persisted(agent.id, _request(name="old-name"))
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.schedule_repository.get_by_agent_id_and_name.return_value = None
        service.schedule_repository.update.side_effect = DuplicateItemError("duplicate")

        with pytest.raises(ClientError):
            await service.update_schedule(
                agent.id, row.id, UpdateAgentRunScheduleRequest(name="new-name")
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceTrigger:
    async def test_trigger_starts_manual_workflow(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.agent_repository.get.return_value = agent

        await service.trigger_schedule(agent.id, row.id)

        temporal_id = build_run_schedule_temporal_id(row.id)
        service.temporal_adapter.trigger_schedule.assert_not_called()
        start_kwargs = service.temporal_adapter.start_workflow.call_args.kwargs
        assert start_kwargs["workflow"] == "ScheduledAgentRunWorkflow"
        assert re.fullmatch(
            rf"{re.escape(temporal_id)}-manual-"
            r"[0-9a-f-]{36}-"
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z",
            start_kwargs["workflow_id"],
        )
        assert start_kwargs["args"] == [row.id, "manual"]
        assert start_kwargs["task_queue"] == "agentex-server"

    async def test_skip_updates_temporal_schedule(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.agent_repository.get.return_value = agent
        scheduled_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)

        await service.skip_schedule_action(agent.id, row.id, scheduled_time)

        temporal_id = build_run_schedule_temporal_id(row.id)
        service.temporal_adapter.skip_schedule_action.assert_awaited_once_with(
            temporal_id, scheduled_time=scheduled_time
        )

    async def test_unskip_updates_temporal_schedule(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_id_or_raise.return_value = row
        service.agent_repository.get.return_value = agent
        scheduled_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)

        await service.unskip_schedule_action(agent.id, row.id, scheduled_time)

        temporal_id = build_run_schedule_temporal_id(row.id)
        service.temporal_adapter.unskip_schedule_action.assert_awaited_once_with(
            temporal_id, scheduled_time=scheduled_time
        )


@pytest.mark.unit
class TestCadenceValidation:
    def test_create_rejects_both_cadences(self):
        with pytest.raises(ValidationError):
            _request(cron_expression="0 9 * * MON", interval_seconds=86400)

    def test_create_rejects_neither_cadence(self):
        with pytest.raises(ValidationError):
            _request(cron_expression=None, interval_seconds=None)

    def test_create_accepts_exactly_one_cadence(self):
        assert _request(cron_expression=None, interval_seconds=3600) is not None

    def test_update_rejects_both_cadences(self):
        with pytest.raises(ValidationError):
            UpdateAgentRunScheduleRequest(
                cron_expression="0 9 * * MON", interval_seconds=86400
            )

    def test_skip_requires_scheduled_time(self):
        with pytest.raises(ValidationError):
            SkipRunScheduleRequest()

    @pytest.mark.parametrize(
        "request_type", [SkipRunScheduleRequest, UnskipRunScheduleRequest]
    )
    def test_skip_and_unskip_reject_naive_scheduled_time(self, request_type):
        with pytest.raises(ValidationError):
            request_type(scheduled_time=datetime(2026, 7, 9, 15, 0))

    def test_update_allows_neither_cadence(self):
        # Partial update changing only an unrelated field is valid.
        assert UpdateAgentRunScheduleRequest(description="new") is not None
