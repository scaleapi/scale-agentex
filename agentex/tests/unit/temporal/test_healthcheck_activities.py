from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from src.domain.entities.agents import AgentStatus
from src.temporal.activities import healthcheck_activities
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


@pytest.mark.unit
@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("failure", ["status", "agent_id", "body", "request"])
async def test_managed_healthcheck_logs_omit_untrusted_values(
    monkeypatch, managed, failure
):
    canary = "healthcheck-private-canary"
    http_client = AsyncMock()
    if failure == "status":
        response = httpx.Response(200, json={"status": canary})
    elif failure == "agent_id":
        response = httpx.Response(200, json={"status": "healthy", "agent_id": canary})
    elif failure == "body":
        response = httpx.Response(200, text=canary * 500)
    else:
        response = None
        http_client.get.side_effect = httpx.ConnectError(
            f"Cannot connect to http://user:{canary}@agent/healthz"
        )
    http_client.get.return_value = response
    monkeypatch.setattr(
        healthcheck_activities, "uses_observability_adapter", lambda: managed
    )
    logger = Mock()
    monkeypatch.setattr(healthcheck_activities, "logger", logger)
    activity = HealthCheckActivities(AsyncMock(), http_client)

    assert await activity.check_status_activity("agent-1", "http://agent") is False

    log_calls = repr(logger.error.call_args_list)
    assert (canary in log_calls) is (not managed and failure != "body")
    assert "agent-1" in log_calls
    if failure == "body":
        assert "status=200" in log_calls
        assert f"bytes={len(response.content)}" in log_calls
