"""Slack Events API ingress — POST /slack/events.

Minimal endpoint whose only job is to pass Slack's one-time Request URL
verification. On save, Slack POSTs ``{"type": "url_verification", "challenge": ...}``
and expects the ``challenge`` echoed back; every other event is acked with 200 so
Slack stops retrying. Real event handling (signature verification, dispatch, reply
delivery) is intentionally not here yet.

Auth-whitelisted (see ``WHITELISTED_ROUTES``) because Slack can't present an SGP
principal — the challenge handshake must reach this route without credentials.
"""

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/slack", tags=["Slack"])


@router.post("/events", summary="Slack Events API ingress")
async def slack_events(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
    return {"ok": True}
