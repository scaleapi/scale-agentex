from unittest.mock import AsyncMock, PropertyMock
from uuid import uuid4

import pytest
from src.adapters.temporal.exceptions import TemporalScheduleNotFoundError
from src.api.schemas.agent_run_schedules import (
    CreateAgentRunScheduleRequest,
    RunScheduleState,
    ScheduleInitialInput,
    UpdateAgentRunScheduleRequest,
)
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
        selector = build_run_schedule_authz_selector("agent-123", "daily-summary")
        assert selector == "run-schedule::agent-123::daily-summary"
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

        # Ownership registered before the Temporal write.
        service.authorization_service.register_resource.assert_called_once()

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

        # The orphaned row and auth entry are compensated.
        service.schedule_repository.delete.assert_called_once_with(id=persisted.id)
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
        authorized = [build_run_schedule_authz_selector(agent.id, "sched-a")]
        result = await service.list_schedules(
            agent.id, authorized_schedule_ids=authorized
        )

        assert result.total == 1
        assert result.run_schedules[0].name == "sched-a"

    async def test_list_none_authorized_means_bypass(self, service, agent):
        rows = [_persisted(agent.id, _request(name="sched-a"))]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        result = await service.list_schedules(agent.id, authorized_schedule_ids=None)

        assert result.total == 1

    async def test_list_does_not_fan_out_to_temporal(self, service, agent):
        # The list path must not issue a describe RPC per row (would scale list
        # latency with the number of schedules). State comes from the row instead.
        rows = [
            _persisted(agent.id, _request(name="sched-a")),
            _persisted(agent.id, _request(name="sched-b")),
        ]
        service.schedule_repository.list_by_agent_id.return_value = rows
        service.agent_repository.get.return_value = agent

        await service.list_schedules(agent.id, authorized_schedule_ids=None)

        service.temporal_adapter.describe_schedule.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceDelete:
    async def test_delete_tolerates_missing_temporal_schedule(self, service, agent):
        # A prior partial delete (Temporal gone, row survived) must still be
        # cleanable: a missing Temporal schedule is treated as success.
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_name_or_raise.return_value = row
        service.temporal_adapter.delete_schedule.side_effect = (
            TemporalScheduleNotFoundError(message="gone", detail="gone")
        )

        result = await service.delete_schedule(agent.id, row.name)

        assert result == row.id
        service.schedule_repository.delete.assert_called_once_with(id=row.id)
        service.authorization_service.deregister_resource.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServicePauseResume:
    async def test_pause_tolerates_missing_temporal_schedule(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_name_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent
        service.temporal_adapter.pause_schedule.side_effect = (
            TemporalScheduleNotFoundError(message="gone", detail="gone")
        )

        response = await service.pause_schedule(agent.id, row.name)

        # The persisted paused flag is still flipped even though the clock is gone.
        assert row.paused is True
        assert response.paused is True
        service.schedule_repository.update.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceUpdate:
    async def test_update_swaps_cron_for_interval(self, service, agent):
        row = _persisted(agent.id, _request())  # cron-based
        service.schedule_repository.get_by_agent_id_and_name_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent

        await service.update_schedule(
            agent.id, row.name, UpdateAgentRunScheduleRequest(interval_seconds=120)
        )

        # Setting interval clears cron, and the new cadence is pushed to Temporal.
        assert row.cron_expression is None
        assert row.interval_seconds == 120
        update_kwargs = service.temporal_adapter.update_schedule.call_args.kwargs
        assert update_kwargs["interval_seconds"] == 120
        assert update_kwargs["cron_expressions"] is None

    async def test_update_rejects_clearing_all_cadences(self, service, agent):
        row = _persisted(agent.id, _request())  # cron-based, no interval
        service.schedule_repository.get_by_agent_id_and_name_or_raise.return_value = row

        # Explicitly nulling cron without supplying an interval leaves no cadence.
        with pytest.raises(ClientError):
            await service.update_schedule(
                agent.id, row.name, UpdateAgentRunScheduleRequest(cron_expression=None)
            )

        service.temporal_adapter.update_schedule.assert_not_called()

    async def test_update_tolerates_missing_temporal_schedule(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_name_or_raise.return_value = row
        service.schedule_repository.update.return_value = row
        service.agent_repository.get.return_value = agent
        service.temporal_adapter.update_schedule.side_effect = (
            TemporalScheduleNotFoundError(message="gone", detail="gone")
        )

        response = await service.update_schedule(
            agent.id, row.name, UpdateAgentRunScheduleRequest(description="new")
        )

        assert response.description == "new"


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunScheduleServiceTrigger:
    async def test_trigger_calls_temporal(self, service, agent):
        row = _persisted(agent.id, _request())
        service.schedule_repository.get_by_agent_id_and_name_or_raise.return_value = row
        service.agent_repository.get.return_value = agent

        await service.trigger_schedule(agent.id, row.name)

        service.temporal_adapter.trigger_schedule.assert_called_once_with(
            build_run_schedule_temporal_id(row.id)
        )
