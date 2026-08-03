"""DEV-ONLY Socket Mode bridge — run the Slack gateway end to end locally, no tunnel.

TEMPORARY. Production ingress is ``POST /slack/events`` (agentex forward proxy + signature
verify). Socket Mode is a different path — the app holds a WebSocket to Slack, so there's
no public URL and no per-event signature. This process:

  1. initializes the real global dependencies (DB / Temporal / Redis / Mongo), the same
     ``startup_global_dependencies()`` the API uses — so dispatch runs for real;
  2. receives ``app_mention`` / ``message`` events over the socket;
  3. feeds each into the real ``SlackGatewayUseCase`` (normalize -> resolve -> dispatch ->
     collect reply -> deliver). No signature check (Socket Mode has none).

Prereqs for a full round-trip:
  - Backing services up (``make dev`` for Postgres/Temporal/Redis/Mongo).
  - A target agent registered + running locally (e.g. ``agentex agents run`` for
    golden-agent) — dispatch HTTP-calls its acp_url, so it must be reachable.
  - Env:
      SLACK_APP_TOKEN=xapp-...     # Socket Mode (scope connections:write)
      SLACK_BOT_TOKEN=xoxb-...     # used by _deliver to post the reply back
      SLACK_GATEWAY_DEV_SKIP_VERIFY=true   # (belt-and-suspenders; this path skips verify anyway)
    Leave SLACK_GATEWAY_ACTING_USER_API_KEY unset locally so dispatch runs with no
    principal (local authz is off); set it only if pointing at an authz-enabled env.

Run (slack_sdk/aiohttp/greenlet added just for this process, not project deps; greenlet
is required by SQLAlchemy's async engine and isn't in the host venv):
  uv run --env-file .env.local --with slack_sdk --with aiohttp --with greenlet \
    python scripts/slack_socket_dev.py
"""

from __future__ import annotations

import asyncio
import os

from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient
from src.config import dependencies
from src.domain.use_cases.slack_gateway_use_case import SlackGatewayUseCase, normalize
from src.utils.logging import make_logger

logger = make_logger(__name__)

_gateway = SlackGatewayUseCase()


def _payload(body: dict) -> dict:
    """Socket Mode delivers the same event_callback shape the HTTP path gets."""
    return {
        "team_id": body.get("team_id", ""),
        "api_app_id": body.get("api_app_id", ""),
        "event": body.get("event", {}),
    }


async def _run(body: dict) -> None:
    inbound = normalize(_payload(body))
    if inbound is None:
        return
    logger.info(
        "[socket-dev] IN channel=%s user=%s thread_ts=%s selector=%r text=%r",
        inbound.channel,
        inbound.user,
        inbound.thread_ts,
        inbound.selector,
        inbound.text,
    )
    try:
        await _gateway._run_turn(
            inbound
        )  # real: resolve -> dispatch -> collect -> deliver
    except Exception:
        logger.exception("[socket-dev] turn failed")


async def _on_request(client: SocketModeClient, req: SocketModeRequest) -> None:
    # Slash commands (e.g. /agents): ACK *with* the response body — in Socket Mode
    # that's how the ephemeral reply is delivered. Verify is skipped in dev, so the
    # form payload dispatches directly.
    if req.type == "slash_commands":
        resp = await _gateway.handle_slash_command(
            body=b"", headers={}, form=req.payload
        )
        await client.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id, payload=resp)
        )
        return
    # Everything else: ACK the envelope immediately (Slack re-sends if we don't),
    # then process async.
    await client.send_socket_mode_response(
        SocketModeResponse(envelope_id=req.envelope_id)
    )
    if req.type == "events_api":
        asyncio.create_task(_run(req.payload))


async def main() -> None:
    logger.info("[socket-dev] initializing dependencies…")
    await dependencies.startup_global_dependencies()

    # DB-first (agent_api_keys), env fallback — same as the production worker.
    app_token = await _gateway._gateway_secret("slack-app-token") or os.environ.get(
        "SLACK_APP_TOKEN", ""
    )
    bot_token = await _gateway._fetch_bot_token()
    client = SocketModeClient(
        app_token=app_token,
        web_client=AsyncWebClient(token=bot_token or None),
    )
    client.socket_mode_request_listeners.append(_on_request)

    logger.info("[socket-dev] connecting to Slack via Socket Mode…")
    await client.connect()
    await asyncio.Event().wait()  # run until interrupted


if __name__ == "__main__":
    asyncio.run(main())
