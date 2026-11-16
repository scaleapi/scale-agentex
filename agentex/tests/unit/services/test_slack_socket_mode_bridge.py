"""Ack and reconnect behaviour of the Slack Socket Mode bridge."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.web.async_client import AsyncWebClient
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.entities.agents import AgentStatus
from src.domain.services import slack_socket_mode_bridge as mod
from src.domain.services.slack_socket_mode_bridge import SlackSocketModeBridge

TRIGGER = AgentAPIKeyEntity(
    id="key-1",
    agent_id="agent-1",
    name="A123",
    api_key_type=AgentAPIKeyType.SLACK,
    api_key="signing-secret",
    app_token_encrypted="ciphertext",
    forward_path="slack/events",
)


def _bridge(handler) -> tuple[SlackSocketModeBridge, MagicMock]:
    agent_repo = MagicMock()
    agent_repo.get = AsyncMock(
        return_value=MagicMock(status=AgentStatus.READY, acp_url="http://agent:8000")
    )
    key_repo = MagicMock()
    key_repo.list_slack_socket_mode_triggers = AsyncMock(return_value=[TRIGGER])
    bridge = SlackSocketModeBridge(
        agent_api_key_repository=key_repo,
        agent_repository=agent_repo,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return bridge, key_repo


def _envelope(retry_attempt: int = 0, retry_reason: str = "") -> SocketModeRequest:
    return SocketModeRequest(
        type="events_api",
        envelope_id="env-1",
        payload={"type": "event_callback", "api_app_id": "A123"},
        retry_attempt=retry_attempt,
        retry_reason=retry_reason,
    )


@pytest.mark.unit
class TestEnvelopeAck:
    async def test_acks_after_agent_accepts(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        bridge, _ = _bridge(handler)
        client = MagicMock(send_socket_mode_response=AsyncMock())

        await bridge._on_request(TRIGGER, client, _envelope())

        assert str(seen[0].url) == "http://agent:8000/slack/events"
        assert "x-slack-retry-num" not in seen[0].headers
        client.send_socket_mode_response.assert_awaited_once()
        assert client.send_socket_mode_response.await_args.args[0].envelope_id == (
            "env-1"
        )

    async def test_no_ack_when_agent_rejects(self):
        bridge, _ = _bridge(lambda request: httpx.Response(503))
        client = MagicMock(send_socket_mode_response=AsyncMock())

        await bridge._on_request(TRIGGER, client, _envelope())

        client.send_socket_mode_response.assert_not_awaited()

    async def test_no_ack_when_agent_misses_deadline(self, monkeypatch):
        monkeypatch.setattr(mod, "ACK_DEADLINE_SECONDS", 0.05)

        async def slow(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1)
            return httpx.Response(200)

        bridge, _ = _bridge(slow)
        client = MagicMock(send_socket_mode_response=AsyncMock())

        await bridge._on_request(TRIGGER, client, _envelope())

        client.send_socket_mode_response.assert_not_awaited()

    async def test_retry_attempt_becomes_retry_headers(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        bridge, _ = _bridge(handler)
        client = MagicMock(send_socket_mode_response=AsyncMock())

        await bridge._on_request(
            TRIGGER, client, _envelope(retry_attempt=2, retry_reason="timeout")
        )

        assert seen[0].headers["x-slack-retry-num"] == "2"
        assert seen[0].headers["x-slack-retry-reason"] == "timeout"


@pytest.mark.unit
class TestRejectedToken:
    async def test_rejected_token_stops_without_retrying(self, monkeypatch):
        monkeypatch.setattr(mod.credential_encryption, "decrypt", lambda _: "xapp-1")
        connections_open = AsyncMock(
            side_effect=SlackApiError(
                "rejected", {"ok": False, "error": "invalid_auth"}
            )
        )
        monkeypatch.setattr(AsyncWebClient, "apps_connections_open", connections_open)
        connect = AsyncMock()
        monkeypatch.setattr(mod._TriggerSocketModeClient, "connect", connect)
        bridge, _ = _bridge(lambda request: httpx.Response(200))

        await bridge.refresh()
        # A later refresh with the same stored token must not try it again.
        await bridge.refresh()

        connections_open.assert_awaited_once()
        connect.assert_not_awaited()
        assert bridge._connections == {}
