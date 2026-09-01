from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.domain.entities.agents import AgentStatus
from src.temporal.activities.healthcheck_activities import HealthCheckActivities


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("current_status", "should_recover"),
    [
        (AgentStatus.UNHEALTHY, True),
        (AgentStatus.READY, False),
        (AgentStatus.BUILD_ONLY, False),
        (AgentStatus.DELETED, False),
        (AgentStatus.FAILED, False),
        (AgentStatus.UNKNOWN, False),
    ],
)
async def test_ready_status_update_only_recovers_unhealthy(
    current_status,
    should_recover,
):
    agent = SimpleNamespace(
        status=current_status,
        status_reason="Existing status reason",
    )
    agent_repo = AsyncMock()
    agent_repo.get.return_value = agent
    activities = HealthCheckActivities(agent_repo, AsyncMock())

    await activities.update_agent_status_activity("agent-1", "Ready")

    agent_repo.get.assert_awaited_once_with(id="agent-1")
    if should_recover:
        assert agent.status == AgentStatus.READY
        assert agent.status_reason == "Agent health check reported Ready"
        agent_repo.update.assert_awaited_once_with(item=agent)
        return

    assert agent.status == current_status
    assert agent.status_reason == "Existing status reason"
    agent_repo.update.assert_not_awaited()
