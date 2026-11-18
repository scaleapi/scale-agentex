"""The Socket Mode bridge end to end, with fakes for Slack and the agent.

Registration goes through the real route, the trigger through real Postgres, and the
socket through the real slack_sdk client. Only Slack's servers and the agent are fake:
``FakeSlack`` serves ``apps.connections.open`` and a Socket Mode WebSocket that sends
``hello`` and then whatever envelopes the test pushes; ``FakeAgent`` records each
forwarded request.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from aiohttp import WSMsgType, web
from cryptography.fernet import Fernet
from multidict import CIMultiDict
from slack_sdk.web.async_client import AsyncWebClient
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.services import slack_socket_mode_bridge as mod
from src.domain.services.slack_socket_mode_bridge import SlackSocketModeBridge
from src.domain.use_cases.slack_gateway_use_case import verify_signature
from src.utils import credential_encryption
from src.utils.ids import orm_id

SLACK_APP_ID = "A123"
SIGNING_SECRET = "signing-secret"
WAIT_SECONDS = 5.0


async def _serve(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return runner, f"http://127.0.0.1:{port}"


@dataclass
class FakeSlack:
    base_url: str = ""
    # The app Slack names in hello, i.e. the app the token belongs to.
    app_id: str = SLACK_APP_ID
    connections_opened: int = 0
    # Each URL is good for one connection attempt; set to fail the first one, as a
    # network blip would.
    fail_first_attempt: bool = False
    tried_urls: list[str] = field(default_factory=list)
    sockets: list[web.WebSocketResponse] = field(default_factory=list)
    acks: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/api/apps.connections.open", self._open)
        app.router.add_get("/link", self._link)
        return app

    async def _open(self, request: web.Request) -> web.Response:
        self.connections_opened += 1
        ws_url = self.base_url.replace("http://", "ws://")
        ws_url += f"/link?ticket={self.connections_opened}"
        return web.json_response({"ok": True, "url": ws_url})

    async def _link(self, request: web.Request) -> web.StreamResponse:
        ticket = request.query["ticket"]
        first_attempt = not self.tried_urls
        if ticket in self.tried_urls:
            self.tried_urls.append(ticket)
            return web.Response(status=401)
        self.tried_urls.append(ticket)
        if first_attempt and self.fail_first_attempt:
            return web.Response(status=503)
        ws = web.WebSocketResponse(autoping=True)
        await ws.prepare(request)
        self.sockets.append(ws)
        await ws.send_json(
            {
                "type": "hello",
                "num_connections": len(self.sockets),
                "connection_info": {"app_id": self.app_id},
            }
        )
        self.connected.set()
        async for message in ws:
            if message.type == WSMsgType.TEXT:
                await self.acks.put(json.loads(message.data)["envelope_id"])
        self.closed.set()
        return ws

    def forget_connections(self) -> None:
        """Clear what registration's own app-id check left behind."""
        self.connections_opened = 0
        self.tried_urls.clear()
        self.sockets.clear()
        self.connected.clear()
        self.closed.clear()

    async def deliver(self, envelope_id: str, retry_attempt: int = 0) -> dict:
        payload = {"type": "event_callback", "api_app_id": SLACK_APP_ID}
        await self.sockets[-1].send_json(
            {
                "type": "events_api",
                "envelope_id": envelope_id,
                "payload": payload,
                "accepts_response_payload": False,
                "retry_attempt": retry_attempt,
                "retry_reason": "timeout" if retry_attempt else "",
            }
        )
        return payload


@dataclass
class FakeAgent:
    status: int = 200
    requests: asyncio.Queue[tuple[str, CIMultiDict[str], bytes]] = field(
        default_factory=asyncio.Queue
    )

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/{tail:.*}", self._receive)
        return app

    async def _receive(self, request: web.Request) -> web.Response:
        body = await request.read()
        await self.requests.put((request.path, CIMultiDict(request.headers), body))
        return web.Response(status=self.status)


@pytest_asyncio.fixture
async def fakes(monkeypatch) -> AsyncIterator[tuple[FakeSlack, FakeAgent]]:
    slack, agent = FakeSlack(), FakeAgent()
    slack_runner, slack.base_url = await _serve(slack.app())
    agent_runner, agent_url = await _serve(agent.app())
    agent.url = agent_url  # type: ignore[attr-defined]

    class ClientAgainstFakeSlack(mod._TriggerSocketModeClient):
        def __init__(self, **kwargs):
            super().__init__(
                web_client=AsyncWebClient(
                    token=kwargs["app_token"], base_url=f"{slack.base_url}/api/"
                ),
                ping_interval=0.5,
                **kwargs,
            )

    monkeypatch.setattr(mod, "_TriggerSocketModeClient", ClientAgainstFakeSlack)
    # Registration's app-id check builds its own client.
    monkeypatch.setattr(
        mod,
        "AsyncWebClient",
        lambda **kwargs: AsyncWebClient(base_url=f"{slack.base_url}/api/", **kwargs),
    )
    credential_encryption.reset_cache()
    monkeypatch.setenv(credential_encryption.ENV_KEY, Fernet.generate_key().decode())
    yield slack, agent
    credential_encryption.reset_cache()
    await slack_runner.cleanup()
    await agent_runner.cleanup()


async def _register(isolated_client, isolated_repositories, agent_url: str):
    await isolated_repositories["agent_repository"].create(
        AgentEntity(
            id=orm_id(),
            name="socket-agent",
            description="Socket Mode end-to-end agent",
            acp_url=agent_url,
            acp_type=ACPType.SYNC,
        )
    )
    return await isolated_client.post(
        "/agent_api_keys/webhook-trigger",
        json={
            "agent_name": "socket-agent",
            "source": "slack",
            "name": SLACK_APP_ID,
            "secret": SIGNING_SECRET,
            "forward_path": "slack/events",
            "app_token": "xapp-1-A123-fake",
        },
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestSlackSocketModeBridgeEndToEnd:
    @pytest_asyncio.fixture
    async def bridge(
        self, isolated_client, isolated_repositories, fakes
    ) -> AsyncIterator[SlackSocketModeBridge]:
        slack, agent = fakes
        response = await _register(isolated_client, isolated_repositories, agent.url)
        assert response.status_code == 200, response.text
        self.key_id = response.json()["key_id"]
        slack.forget_connections()

        async with httpx.AsyncClient() as http_client:
            bridge = SlackSocketModeBridge(
                agent_api_key_repository=isolated_repositories[
                    "agent_api_key_repository"
                ],
                agent_repository=isolated_repositories["agent_repository"],
                http_client=http_client,
            )
            yield bridge
            await bridge.stop()

    async def test_event_reaches_the_agent_signed_and_is_acked(self, bridge, fakes):
        slack, agent = fakes
        await bridge.refresh()
        await asyncio.wait_for(slack.connected.wait(), WAIT_SECONDS)

        payload = await slack.deliver("env-1")
        path, headers, body = await asyncio.wait_for(agent.requests.get(), WAIT_SECONDS)

        assert path == "/slack/events"
        assert json.loads(body) == payload
        assert verify_signature(
            SIGNING_SECRET,
            headers["X-Slack-Request-Timestamp"],
            headers["X-Slack-Signature"],
            body,
        )
        assert "X-Slack-Retry-Num" not in headers
        assert await asyncio.wait_for(slack.acks.get(), WAIT_SECONDS) == "env-1"

    async def test_unaccepted_event_is_acked_only_on_a_redelivery_the_agent_takes(
        self, bridge, fakes
    ):
        slack, agent = fakes
        await bridge.refresh()
        await asyncio.wait_for(slack.connected.wait(), WAIT_SECONDS)
        agent.status = 503

        await slack.deliver("env-1")
        await asyncio.wait_for(agent.requests.get(), WAIT_SECONDS)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(slack.acks.get(), mod.ACK_DEADLINE_SECONDS)

        agent.status = 200
        await slack.deliver("env-1", retry_attempt=1)
        _, headers, _ = await asyncio.wait_for(agent.requests.get(), WAIT_SECONDS)

        assert headers["X-Slack-Retry-Num"] == "1"
        assert headers["X-Slack-Retry-Reason"] == "timeout"
        assert await asyncio.wait_for(slack.acks.get(), WAIT_SECONDS) == "env-1"

    async def test_deleting_the_trigger_closes_the_socket(
        self, bridge, fakes, isolated_client
    ):
        slack, _ = fakes
        await bridge.refresh()
        await asyncio.wait_for(slack.connected.wait(), WAIT_SECONDS)

        response = await isolated_client.delete(f"/agent_api_keys/{self.key_id}")
        assert response.status_code == 200, response.text
        await bridge.refresh()

        await asyncio.wait_for(slack.closed.wait(), WAIT_SECONDS)
        assert bridge._connections == {}
        assert slack.connections_opened == 1

    async def test_a_connection_stuck_on_a_dead_url_is_reopened(
        self, bridge, fakes, monkeypatch
    ):
        slack, _ = fakes
        slack.fail_first_attempt = True

        await bridge.refresh()
        while len(slack.tried_urls) < 3:
            await asyncio.sleep(0.1)
        # slack_sdk keeps retrying the URL it was given, which is now dead.
        assert set(slack.tried_urls) == {"1"}
        assert not slack.connected.is_set()

        monkeypatch.setattr(mod, "REFRESH_INTERVAL_SECONDS", 0)
        await bridge.refresh()

        await asyncio.wait_for(slack.connected.wait(), WAIT_SECONDS)
        assert slack.connections_opened == 2

    async def test_registration_refuses_a_token_for_another_app(
        self, isolated_client, isolated_repositories, fakes
    ):
        slack, agent = fakes
        slack.app_id = "B999"

        response = await _register(isolated_client, isolated_repositories, agent.url)

        assert response.status_code == 400, response.text
        assert "B999" in response.text
        key_repo = isolated_repositories["agent_api_key_repository"]
        assert await key_repo.list_slack_socket_mode_apps() == []

    async def test_bridge_drops_a_token_that_names_another_app(self, bridge, fakes):
        slack, agent = fakes
        slack.app_id = "B999"

        await bridge.refresh()
        await asyncio.wait_for(slack.closed.wait(), WAIT_SECONDS)
        await bridge.refresh()

        assert bridge._connections == {}
        assert slack.connections_opened == 1
        assert agent.requests.empty()
