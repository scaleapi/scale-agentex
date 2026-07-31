"""Production Socket Mode worker — the always-on outbound WebSocket to Slack.

Runs as a dedicated Deployment (fixed replicas, autoscaling OFF): each replica
holds ONE Socket Mode connection and dispatches events through the real
``SlackGatewayUseCase``. Because the connection is outbound, this works from a
network-restricted deployment with no inbound endpoint — the production
counterpart to the dev bridge (``scripts/slack_socket_dev.py``).

Hardening over the dev bridge:
  - graceful shutdown on SIGTERM/SIGINT (close the socket, then exit),
  - a liveness HTTP endpoint (``/healthz``) reporting socket-connected state,
  - event dedup (Socket Mode is at-least-once) on Slack's ``event_id`` via Redis,
  - slash-command handling (``/agents``).

Run 2 pods for HA: Slack routes each event to a single open connection, so
replicas give redundancy across rolling deploys/restarts without duplicate
delivery. ``slack_sdk`` auto-reconnects on drops; k8s restarts a wedged pod.

Run:  python -m src.slack.socket_worker
Creds: the Slack app token (xapp) and bot token (xoxb) are read from the DB
      (``agent_api_keys``, the same throwaway store as the signing secret) via
      the gateway, falling back to env (SLACK_APP_TOKEN / SLACK_BOT_TOKEN) for
      local dev — so no write to the platform's IAM-locked AWS secret is needed.
      Plus the usual DATABASE_URL / REDIS_URL / TEMPORAL_ADDRESS / MONGODB_*.

slack_sdk / aiohttp are imported lazily inside the runtime methods so this module
stays importable (and unit-testable) without them present.
"""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

import redis.asyncio as redis

from src.config import dependencies
from src.config.dependencies import GlobalDependencies
from src.domain.use_cases.slack_gateway_use_case import SlackGatewayUseCase, normalize
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Slack retries redelivery within minutes; a short TTL guards against reprocessing
# the same event on reconnect/redelivery without growing Redis unbounded.
_DEDUP_TTL_SECONDS = int(os.getenv("SLACK_SOCKET_DEDUP_TTL", "600"))
_HEALTH_PORT = int(os.getenv("SLACK_SOCKET_HEALTH_PORT", "8080"))

# DB key (agent_api_keys, type SLACK) for the Socket Mode app-level token, mirroring
# the gateway's slack-bot-token / slack-signing-secret naming.
_APP_TOKEN_NAME = "slack-app-token"


class SocketWorker:
    """One outbound Socket Mode connection per instance; run 2 pods for HA."""

    def __init__(self) -> None:
        self._gateway = SlackGatewayUseCase()
        self._client: Any = None
        self._stop = asyncio.Event()
        self._redis: redis.Redis | None = None

    async def _already_processed(self, event_id: str | None) -> bool:
        """Socket Mode is at-least-once — dedup on Slack's ``event_id`` via a Redis
        ``SET NX`` with a short TTL. Returns True when the event was already seen
        (skip it). Fail-open (False) if there's no ``event_id`` or no Redis, and on
        any Redis error, so dedup can never block a legitimate turn."""
        if not event_id or self._redis is None:
            return False
        try:
            first_time = await self._redis.set(
                f"slack:dedup:{event_id}", "1", nx=True, ex=_DEDUP_TTL_SECONDS
            )
            return not first_time
        except Exception:  # noqa: BLE001 - dedup is best-effort; never block a turn
            logger.warning(
                "[slack-socket] dedup check failed; processing anyway", exc_info=True
            )
            return False

    @staticmethod
    def _payload(body: dict) -> dict:
        """Socket Mode delivers the same event_callback shape the HTTP path parses."""
        return {
            "team_id": body.get("team_id", ""),
            "api_app_id": body.get("api_app_id", ""),
            "event": body.get("event", {}),
        }

    async def _handle_event(self, body: dict) -> None:
        if await self._already_processed(body.get("event_id")):
            logger.info(
                "[slack-socket] duplicate event %s skipped", body.get("event_id")
            )
            return
        inbound = normalize(self._payload(body))
        if inbound is None:
            return
        try:
            await self._gateway._run_turn(
                inbound
            )  # resolve -> dispatch -> collect -> deliver
        except Exception:  # noqa: BLE001 - one bad turn must not kill the worker
            logger.exception("[slack-socket] turn failed")

    async def _on_request(self, client: Any, req: Any) -> None:
        from slack_sdk.socket_mode.response import SocketModeResponse

        # Slash commands (/agents): ACK *with* the response body — that's how the
        # ephemeral reply is delivered in Socket Mode. Verify is skipped (the socket
        # itself is authenticated), so the form payload dispatches directly.
        if req.type == "slash_commands":
            resp = await self._gateway.handle_slash_command(
                body=b"", headers={}, form=req.payload
            )
            await client.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id, payload=resp)
            )
            return
        # Everything else: ACK the envelope immediately (Slack redelivers otherwise),
        # then process out-of-band so the ack isn't blocked by the turn.
        await client.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )
        if req.type == "events_api":
            asyncio.create_task(self._handle_event(req.payload))

    def _connected(self) -> bool:
        client = self._client
        if client is None:
            return False
        is_conn = getattr(client, "is_connected", None)
        return bool(is_conn()) if callable(is_conn) else True

    async def _start_health_server(self) -> Any:
        """Liveness endpoint for the k8s probe: 200 while the socket is connected,
        503 otherwise so a wedged pod gets restarted."""
        from aiohttp import web

        async def health(_req: Any) -> Any:
            ok = self._connected()
            return web.json_response({"connected": ok}, status=200 if ok else 503)

        app = web.Application()
        app.router.add_get("/healthz", health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", _HEALTH_PORT).start()
        logger.info("[slack-socket] health server on :%d/healthz", _HEALTH_PORT)
        return runner

    async def run(self) -> None:
        from slack_sdk.socket_mode.aiohttp import SocketModeClient
        from slack_sdk.web.async_client import AsyncWebClient

        logger.info("[slack-socket] initializing dependencies…")
        await dependencies.startup_global_dependencies()
        pool = GlobalDependencies().redis_pool
        if pool is not None:
            self._redis = redis.Redis(connection_pool=pool)

        health_runner = await self._start_health_server()

        # App + bot tokens from the DB (env fallback for local) — no AWS-secret write.
        app_token = await self._gateway._gateway_secret(_APP_TOKEN_NAME) or os.getenv(
            "SLACK_APP_TOKEN", ""
        )
        if not app_token:
            raise RuntimeError(
                f"no Slack app token — store one in agent_api_keys (name={_APP_TOKEN_NAME!r}, "
                "type SLACK) or set SLACK_APP_TOKEN"
            )
        bot_token = await self._gateway._fetch_bot_token()

        self._client = SocketModeClient(
            app_token=app_token,
            web_client=AsyncWebClient(token=bot_token or None),
        )
        self._client.socket_mode_request_listeners.append(self._on_request)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop.set)

        logger.info("[slack-socket] connecting to Slack via Socket Mode…")
        await self._client.connect()
        logger.info("[slack-socket] connected; awaiting events (SIGTERM to stop)")
        await self._stop.wait()

        logger.info("[slack-socket] shutdown signal received — closing socket…")
        try:
            await self._client.disconnect()
        except Exception:  # noqa: BLE001
            logger.warning("[slack-socket] disconnect error", exc_info=True)
        await health_runner.cleanup()


def main() -> None:
    asyncio.run(SocketWorker().run())


if __name__ == "__main__":
    main()
