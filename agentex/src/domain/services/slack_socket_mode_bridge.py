"""Receive Slack webhook-trigger events over Socket Mode instead of HTTP.

A Slack trigger registered with an app-level token gets one Socket Mode connection
per bridge process (``src/run_slack_socket_mode_bridge.py``), never per API worker:
Slack caps an app at 10 open connections. Slack delivers each envelope to one of the
app's connections, so several bridge replicas don't duplicate work, and when one
closes its socket the others keep receiving. Each ``events_api`` envelope is forwarded to
the agent exactly as ``/agents/forward`` would forward the HTTP delivery, signed with the
trigger's signing secret as Slack signs one, and acked
only once the agent has accepted it: an unacked envelope is redelivered by Slack,
which is the retry path when an agent is slow or down.

A Slack app must be owned by exactly one Socket Mode client. If an agent (or another
agentex environment) also holds a socket for the same app, Slack splits the events
between them.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.config.dependencies import database_async_read_write_session_maker
from src.domain.entities.agent_api_keys import (
    AgentAPIKeyEntity,
    SlackSocketModeAppEntity,
)
from src.domain.entities.agents import AgentStatus
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.utils import credential_encryption
from src.utils.acp_url import resolve_acp_url
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Slack expects an ack within 3s; leave headroom for the ack frame itself.
ACK_DEADLINE_SECONDS = 2.5
REFRESH_INTERVAL_SECONDS = 60.0

# apps.connections.open errors that no retry can fix.
REJECTED_TOKEN_ERRORS = frozenset(
    {
        "invalid_auth",
        "token_revoked",
        "account_inactive",
        "not_allowed_token_type",
        "not_authed",
        "token_expired",
    }
)


class AppTokenRejected(Exception):
    """Slack refused the app token; the connection for it has been stopped."""


class _TriggerSocketModeClient(SocketModeClient):
    def __init__(self, trigger: AgentAPIKeyEntity, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.trigger = trigger
        self.rejected = False

    async def issue_new_wss_url(self) -> str:
        # slack_sdk also calls this on every reconnect, and on a revoked token its
        # connect/monitor loops would retry (and log a traceback) every few seconds
        # forever. The base method still handles rate limiting (it waits out
        # Retry-After); only the errors no retry can fix stop the connection.
        try:
            return await super().issue_new_wss_url()
        except SlackApiError as exc:
            error = exc.response.get("error")
            if error in REJECTED_TOKEN_ERRORS:
                # slack_sdk's loops all run `while not self.closed`.
                self.closed = True
                self.auto_reconnect_enabled = False
                self.rejected = True
                logger.error(
                    "Slack rejected the app token for Socket Mode trigger %s "
                    "(app %s, agent %s): %s. Not reconnecting until the trigger is "
                    "re-registered with a new token.",
                    self.trigger.id,
                    self.trigger.name,
                    self.trigger.agent_id,
                    error,
                )
                raise AppTokenRejected(error) from exc
            raise


def _slack_signature_headers(
    signing_secret: str, body: bytes, timestamp: int
) -> dict[str, str]:
    """The headers Slack sets on an HTTP delivery, for the same body.

    An agent that checks Slack's v0 signature itself then accepts a socket delivery
    exactly as it would an HTTP one.
    """
    basis = f"v0:{timestamp}:".encode() + body
    digest = hmac.new(signing_secret.encode(), basis, hashlib.sha256).hexdigest()
    return {
        "x-slack-request-timestamp": str(timestamp),
        "x-slack-signature": f"v0={digest}",
    }


@dataclass
class _Connection:
    app_token_encrypted: str
    client: _TriggerSocketModeClient
    # Held so the task isn't garbage-collected while connect() is still retrying.
    connect_task: asyncio.Task


class SlackSocketModeBridge:
    def __init__(
        self,
        agent_api_key_repository: AgentAPIKeyRepository,
        agent_repository: AgentRepository,
        http_client: httpx.AsyncClient,
    ):
        self._agent_api_key_repo = agent_api_key_repository
        self._agent_repo = agent_repository
        self._http_client = http_client
        self._connections: dict[str, _Connection] = {}
        # (trigger id, ciphertext) pairs whose token is known bad. Keyed on the
        # ciphertext so a re-registered token is tried again.
        self._rejected: set[tuple[str, str]] = set()
        self._task: asyncio.Task | None = None
        # Set once the trigger list has loaded. Deliberately not tied to sockets
        # being connected: one revoked token must not take the bridge out.
        self.ready = False

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for trigger_id in list(self._connections):
            await self._close(trigger_id)

    async def _run(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception:
                logger.exception("Refreshing Slack Socket Mode triggers failed")
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    async def refresh(self) -> None:
        """Open connections for new triggers and close them for removed ones."""
        served = {
            trigger.id: (trigger, app)
            for trigger, app in await self._agent_api_key_repo.list_slack_socket_mode_apps()
        }
        self.ready = True
        for trigger_id, connection in list(self._connections.items()):
            current = served.get(trigger_id)
            if (
                current is None
                or current[1].app_token_encrypted != connection.app_token_encrypted
                or connection.client.closed
            ):
                if connection.client.rejected:
                    self._rejected.add((trigger_id, connection.app_token_encrypted))
                await self._close(trigger_id)
        for trigger, app in served.values():
            if trigger.id in self._connections:
                continue
            if (trigger.id, app.app_token_encrypted) in self._rejected:
                continue
            await self._open(trigger, app)

    async def _open(
        self, trigger: AgentAPIKeyEntity, app: SlackSocketModeAppEntity
    ) -> None:
        try:
            app_token = credential_encryption.decrypt(app.app_token_encrypted)
        except credential_encryption.CredentialEncryptionError as exc:
            logger.error(
                "Cannot read the app token for Slack Socket Mode trigger %s: %s",
                trigger.id,
                exc,
            )
            self._rejected.add((trigger.id, app.app_token_encrypted))
            return

        client = _TriggerSocketModeClient(trigger=trigger, app_token=app_token)
        client.socket_mode_request_listeners.append(
            partial(self._on_request, trigger, app)
        )
        try:
            # Called once up front so a rejected token stops here instead of
            # inside connect()'s retry loop; connect() reuses the URL.
            client.wss_uri = await client.issue_new_wss_url()
        except AppTokenRejected:
            self._rejected.add((trigger.id, app.app_token_encrypted))
            await client.close()
            return
        except Exception as exc:
            # Transient (network, rate limit): connect() fetches a URL and retries.
            logger.warning(
                "Opening Slack Socket Mode for trigger %s failed (%s); retrying",
                trigger.id,
                type(exc).__name__,
            )
        self._connections[trigger.id] = _Connection(
            app_token_encrypted=app.app_token_encrypted,
            client=client,
            connect_task=asyncio.create_task(client.connect()),
        )
        logger.info(
            "Slack Socket Mode connecting for trigger %s (app %s, agent %s)",
            trigger.id,
            trigger.name,
            trigger.agent_id,
        )

    async def _close(self, trigger_id: str) -> None:
        connection = self._connections.pop(trigger_id)
        connection.connect_task.cancel()
        try:
            await connection.client.close()
        except Exception:
            logger.exception(
                "Closing Slack Socket Mode connection for trigger %s failed",
                trigger_id,
            )

    async def _on_request(
        self,
        trigger: AgentAPIKeyEntity,
        app: SlackSocketModeAppEntity,
        client: SocketModeClient,
        request: SocketModeRequest,
    ) -> None:
        if request.type != "events_api":
            # Interactivity and slash commands have no HTTP forward equivalent on
            # a webhook trigger; leaving them unacked surfaces the gap to the user.
            logger.warning(
                "Ignoring Slack Socket Mode %s envelope for trigger %s",
                request.type,
                trigger.id,
            )
            return
        if await self.forward_event(
            trigger,
            app,
            request.payload,
            retry_attempt=request.retry_attempt,
            retry_reason=request.retry_reason,
        ):
            await client.send_socket_mode_response(
                SocketModeResponse(envelope_id=request.envelope_id)
            )

    async def forward_event(
        self,
        trigger: AgentAPIKeyEntity,
        app: SlackSocketModeAppEntity,
        payload: dict,
        retry_attempt: int | None,
        retry_reason: str | None,
    ) -> bool:
        """POST an Events API payload to the trigger's agent route.

        Returns whether the agent accepted it (2xx) within the ack deadline, or
        declined a redelivery with ``X-Slack-No-Retry: 1`` as it can over HTTP; the
        caller acks only then, so anything else is redelivered by Slack.
        """
        body = json.dumps(payload).encode()
        headers = {
            "content-type": "application/json",
            **_slack_signature_headers(trigger.api_key, body, int(time.time())),
        }
        # Over HTTP Slack sends these only on redeliveries; the first delivery
        # over a socket has retry_attempt 0.
        if retry_attempt:
            headers["x-slack-retry-num"] = str(retry_attempt)
            if retry_reason:
                headers["x-slack-retry-reason"] = retry_reason
        try:
            async with asyncio.timeout(ACK_DEADLINE_SECONDS):
                agent = await self._agent_repo.get(id=trigger.agent_id)
                if agent.status == AgentStatus.DELETED or not agent.acp_url:
                    logger.warning(
                        "Slack Socket Mode trigger %s: agent %s is deleted or has "
                        "no ACP URL",
                        trigger.id,
                        trigger.agent_id,
                    )
                    return False
                url = f"{resolve_acp_url(agent.acp_url)}/{app.forward_path.lstrip('/')}"
                response = await self._http_client.post(
                    url, content=body, headers=headers
                )
        except (TimeoutError, httpx.HTTPError, ItemDoesNotExist) as exc:
            logger.warning(
                "Forwarding Slack Socket Mode event for trigger %s failed (%s); "
                "leaving it unacked for redelivery",
                trigger.id,
                type(exc).__name__,
            )
            return False
        if response.is_success:
            return True
        if response.headers.get("x-slack-no-retry") == "1":
            logger.info(
                "Agent %s answered %s with X-Slack-No-Retry to a Slack Socket Mode "
                "event for trigger %s; acking so Slack does not redeliver it",
                trigger.agent_id,
                response.status_code,
                trigger.id,
            )
            return True
        logger.warning(
            "Agent %s answered %s to a Slack Socket Mode event for trigger %s; "
            "leaving it unacked for redelivery",
            trigger.agent_id,
            response.status_code,
            trigger.id,
        )
        return False


def create_slack_socket_mode_bridge(
    engine: AsyncEngine, http_client: httpx.AsyncClient
) -> SlackSocketModeBridge:
    """Build the bridge on one database engine and HTTP client.

    The bridge only reads triggers and agents, so every session uses ``engine``.
    """
    session_maker = database_async_read_write_session_maker(engine)
    return SlackSocketModeBridge(
        agent_api_key_repository=AgentAPIKeyRepository(session_maker, session_maker),
        agent_repository=AgentRepository(session_maker, session_maker),
        http_client=http_client,
    )
