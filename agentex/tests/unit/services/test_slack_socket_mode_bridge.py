"""Ack and reconnect behaviour of the Slack Socket Mode bridge."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import slack_sdk.socket_mode.async_client as sdk_async_client
import src.run_slack_socket_mode_bridge as entrypoint
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.web.slack_response import SlackResponse
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.entities.agents import AgentStatus
from src.domain.services import slack_socket_mode_bridge as mod
from src.domain.services.slack_socket_mode_bridge import SlackSocketModeBridge
from src.domain.use_cases.slack_gateway_use_case import verify_signature

TRIGGER = AgentAPIKeyEntity(
    id="key-1",
    agent_id="agent-1",
    name="A123",
    api_key_type=AgentAPIKeyType.SLACK,
    api_key="signing-secret",
    slack_socket_mode_app_token_encrypted="ciphertext",
    slack_socket_mode_forward_path="slack/events",
)


def _bridge(handler, triggers=(TRIGGER,)) -> tuple[SlackSocketModeBridge, MagicMock]:
    agent_repo = MagicMock()
    agent_repo.get = AsyncMock(
        return_value=MagicMock(status=AgentStatus.READY, acp_url="http://agent:8000")
    )
    key_repo = MagicMock()
    key_repo.list_slack_socket_mode_triggers = AsyncMock(return_value=list(triggers))
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

    async def test_forward_passes_slacks_own_signature_check(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        bridge, _ = _bridge(handler)
        client = MagicMock(send_socket_mode_response=AsyncMock())

        await bridge._on_request(TRIGGER, client, _envelope())

        forwarded = seen[0]
        assert verify_signature(
            TRIGGER.api_key,
            forwarded.headers["x-slack-request-timestamp"],
            forwarded.headers["x-slack-signature"],
            forwarded.content,
        )
        assert not verify_signature(
            "another-secret",
            forwarded.headers["x-slack-request-timestamp"],
            forwarded.headers["x-slack-signature"],
            forwarded.content,
        )

    async def test_acks_when_agent_declines_redelivery(self):
        bridge, _ = _bridge(
            lambda request: httpx.Response(400, headers={"X-Slack-No-Retry": "1"})
        )
        client = MagicMock(send_socket_mode_response=AsyncMock())

        await bridge._on_request(TRIGGER, client, _envelope())

        client.send_socket_mode_response.assert_awaited_once()


@pytest.mark.unit
class TestOneConnectionPerApp:
    async def test_only_the_earliest_trigger_for_an_app_connects(self, monkeypatch):
        monkeypatch.setattr(mod.credential_encryption, "decrypt", lambda _: "xapp-1")
        monkeypatch.setattr(
            AsyncWebClient,
            "apps_connections_open",
            AsyncMock(return_value={"url": "wss://example.invalid"}),
        )
        monkeypatch.setattr(mod._TriggerSocketModeClient, "connect", AsyncMock())
        later = TRIGGER.model_copy(
            update={
                "id": "key-2",
                "agent_id": "agent-2",
                "created_at": datetime(2026, 2, 1, tzinfo=UTC),
            }
        )
        earlier = TRIGGER.model_copy(
            update={"created_at": datetime(2026, 1, 1, tzinfo=UTC)}
        )
        bridge, _ = _bridge(lambda request: httpx.Response(200), [later, earlier])

        await bridge.refresh()

        assert list(bridge._connections) == [earlier.id]
        await bridge.stop()


@pytest.mark.unit
class TestRateLimited:
    async def test_rate_limit_waits_and_retries_instead_of_rejecting(self, monkeypatch):
        rate_limited = SlackApiError(
            "ratelimited",
            SlackResponse(
                client=None,
                http_verb="POST",
                api_url="https://slack.com/api/apps.connections.open",
                req_args={},
                data={"ok": False, "error": "ratelimited"},
                headers={"Retry-After": "7"},
                status_code=429,
            ),
        )
        monkeypatch.setattr(
            AsyncWebClient,
            "apps_connections_open",
            AsyncMock(side_effect=[rate_limited, {"url": "wss://example.invalid"}]),
        )
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        monkeypatch.setattr(sdk_async_client.asyncio, "sleep", fake_sleep)
        client = mod._TriggerSocketModeClient(trigger=TRIGGER, app_token="xapp-1")

        assert await client.issue_new_wss_url() == "wss://example.invalid"
        assert slept == [7]
        assert not client.rejected
        await client.close()


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
        # A dead token must not hold the bridge out of readiness.
        assert bridge.ready


@pytest.mark.unit
class TestShutdown:
    async def test_stop_closes_open_sockets(self, monkeypatch):
        monkeypatch.setattr(mod.credential_encryption, "decrypt", lambda _: "xapp-1")
        monkeypatch.setattr(
            AsyncWebClient,
            "apps_connections_open",
            AsyncMock(return_value={"url": "wss://example.invalid"}),
        )
        monkeypatch.setattr(mod._TriggerSocketModeClient, "connect", AsyncMock())
        bridge, _ = _bridge(lambda request: httpx.Response(200))
        await bridge.refresh()
        client = bridge._connections[TRIGGER.id].client

        await bridge.stop()

        assert client.closed
        assert client.aiohttp_client_session.closed
        assert bridge._connections == {}

    async def test_cancelling_main_stops_bridge_and_disposes_engine(self, monkeypatch):
        fake = MagicMock(start=AsyncMock(), stop=AsyncMock(), ready=True)
        engine = MagicMock(dispose=AsyncMock())
        monkeypatch.setattr(
            entrypoint.credential_encryption, "is_configured", lambda: True
        )
        monkeypatch.setattr(entrypoint, "create_engine", lambda url: engine)
        monkeypatch.setattr(
            entrypoint, "create_slack_socket_mode_bridge", lambda engine, client: fake
        )

        task = asyncio.create_task(entrypoint.main(probe_port=0))
        while not fake.start.await_count:
            await asyncio.sleep(0)
        # _run_cli turns SIGTERM into this cancellation.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        fake.stop.assert_awaited_once()
        engine.dispose.assert_awaited_once()

    async def test_refuses_to_start_without_encryption_key(self, monkeypatch):
        create_engine = MagicMock()
        monkeypatch.setattr(entrypoint, "create_engine", create_engine)
        monkeypatch.setattr(
            entrypoint.credential_encryption, "is_configured", lambda: False
        )

        with pytest.raises(SystemExit):
            await entrypoint.main(probe_port=0)
        create_engine.assert_not_called()
