"""Channels API: external surfaces (webhook now, Slack later) that drive agent turns.

The webhook endpoint is auth-whitelisted in `middleware_utils.WHITELISTED_ROUTES`
(it bypasses the agentex API-key auth) and instead verifies a per-route shared
secret / HMAC inside the channel. Each route binds to one agent and an opaque
`params` dict forwarded verbatim to task/create (agentex does not interpret it —
the bound agent does).

Route bindings live in the CHANNELS_WEBHOOK_ROUTES env var (JSON) for now — the
seam where a real per-config store (resolving a saved agent_config_id) plugs in later:

    CHANNELS_WEBHOOK_ROUTES='{"demo": {"secret": "<shared-secret>",
        "agent_name": "golden-agent",
        "params": {"system_prompt": "You are ...", "mcps": []}}}'
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Query, Request

from src.domain.channels.base import ChannelBinding
from src.domain.channels.router import ChannelRouter
from src.domain.channels.webhook import MAX_BODY_BYTES, WebhookChannel
from src.domain.services.task_message_service import DTaskMessageService
from src.domain.use_cases.agents_acp_use_case import DAgentsACPUseCase
from src.domain.use_cases.agents_use_case import DAgentsUseCase
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/channels", tags=["Channels"])

# Channel registry — add "slack": SlackChannel() here when it lands.
_WEBHOOK = WebhookChannel()


def _webhook_binding(route_id: str) -> ChannelBinding | None:
    """Resolve a webhook route's binding. Env-backed seam; replace with a config store."""
    raw = os.environ.get("CHANNELS_WEBHOOK_ROUTES")
    if not raw:
        return None
    try:
        routes = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("[channels] CHANNELS_WEBHOOK_ROUTES is not valid JSON")
        return None
    cfg = routes.get(route_id)
    if not isinstance(cfg, dict) or not cfg.get("secret") or not cfg.get("agent_name"):
        return None
    # `params` is opaque — forwarded verbatim to task/create; agentex does not
    # interpret it (an agent like golden-agent reads system_prompt/mcps/etc. there).
    params = cfg.get("params")
    return ChannelBinding(
        secret=cfg["secret"],
        agent_name=cfg["agent_name"],
        params=params if isinstance(params, dict) else {},
    )


@router.post(
    "/webhook/{route_id}",
    summary="Generic webhook channel",
    description="Authenticated webhook ingress: verifies a per-route secret/HMAC and "
    "drives an agent turn. Auth is whitelisted at the middleware; the channel verifies "
    "the route secret instead.",
)
async def handle_webhook(
    route_id: str,
    request: Request,
    agents_acp_use_case: DAgentsACPUseCase,
    agents_use_case: DAgentsUseCase,
    task_message_service: DTaskMessageService,
    wait: bool = Query(
        False,
        description="If true, wait for the agent's reply and return it (for synchronous "
        "callers). Default false: return immediately with the task_id.",
    ),
) -> dict:
    binding = _webhook_binding(route_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="unknown route")

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    if not _WEBHOOK.authenticate(binding, request, raw):
        raise HTTPException(status_code=401, detail="unauthorized")
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(status_code=400, detail="expected application/json")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="json body must be an object")

    # Resolve the agent's ACP type so the router picks the right turn method
    # (sync -> message/send returns the reply inline; async -> event/send).
    agent = await agents_use_case.get(name=binding.agent_name)

    inbound = _WEBHOOK.to_inbound(route_id, body)
    router_ = ChannelRouter(agents_acp_use_case, task_message_service)
    result = await router_.dispatch(inbound, binding, agent.acp_type)

    # A plain webhook has no outbound push (supports_outbound is False) — its reply is
    # the HTTP response. Sync agents reply inline; for async, `wait` streams it back.
    # A push channel (Slack) would instead: reply = result.reply or await_reply(...);
    # await deliver_reply(channel, peer_id, reply).
    reply = result.reply
    if reply is None and wait:
        reply = await router_.await_reply(result.task_id, result.after_id)

    response = {
        "ok": True,
        "channel": "webhook",
        "route_id": route_id,
        "task_id": result.task_id,
    }
    if reply is not None:
        response["reply"] = reply
    return response
