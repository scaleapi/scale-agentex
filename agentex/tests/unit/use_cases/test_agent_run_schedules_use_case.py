from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.api.schemas.agent_run_schedules import (
    CreateAgentRunScheduleRequest,
    ScheduleInitialInput,
)
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.exceptions import ClientError
from src.domain.use_cases.agent_run_schedules_use_case import (
    AgentRunSchedulesUseCase,
)


@pytest.fixture
def mock_service():
    mock = AsyncMock()
    return mock


@pytest.fixture
def use_case(mock_service):
    return AgentRunSchedulesUseCase(run_schedule_service=mock_service)


@pytest.fixture
def agent():
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://acp.example.com",
    )


def _request(**overrides) -> CreateAgentRunScheduleRequest:
    payload: dict = {
        "name": "daily-summary",
        "cron_expression": "0 17 * * MON-FRI",
        "initial_input": ScheduleInitialInput(content="hello"),
    }
    payload.update(overrides)
    return CreateAgentRunScheduleRequest(**payload)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentRunSchedulesUseCase:
    async def test_create_with_cron_delegates(self, use_case, mock_service, agent):
        request = _request()
        mock_service.create_schedule.return_value = "ok"
        creator = {"user_id": "u1", "account_id": "a1"}

        result = await use_case.create_schedule(agent, request, creator)

        assert result == "ok"
        mock_service.create_schedule.assert_called_once_with(agent, request, creator)

    async def test_create_with_interval_delegates(self, use_case, mock_service, agent):
        request = _request(cron_expression=None, interval_seconds=30)
        mock_service.create_schedule.return_value = "ok"

        await use_case.create_schedule(agent, request, {"user_id": "u1"})

        mock_service.create_schedule.assert_called_once()

    async def test_create_requires_a_cadence(self, use_case, agent):
        request = _request(cron_expression=None, interval_seconds=None)

        with pytest.raises(ClientError) as exc:
            await use_case.create_schedule(agent, request, {"user_id": "u1"})

        assert "cron_expression or interval_seconds" in str(exc.value)

    async def test_create_rejects_both_cadences(self, use_case, agent):
        request = _request(cron_expression="0 0 * * *", interval_seconds=30)

        with pytest.raises(ClientError) as exc:
            await use_case.create_schedule(agent, request, {"user_id": "u1"})

        assert "only one" in str(exc.value)

    async def test_pause_resume_delete_delegate(self, use_case, mock_service, agent):
        await use_case.pause_schedule(agent.id, "daily-summary", note="n")
        mock_service.pause_schedule.assert_called_once_with(
            agent.id, "daily-summary", note="n"
        )

        await use_case.resume_schedule(agent.id, "daily-summary")
        mock_service.resume_schedule.assert_called_once_with(
            agent.id, "daily-summary", note=None
        )

        await use_case.delete_schedule(agent.id, "daily-summary")
        mock_service.delete_schedule.assert_called_once_with(agent.id, "daily-summary")
