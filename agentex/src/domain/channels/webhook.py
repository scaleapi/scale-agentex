"""WebhookChannel: generic HTTP ingress (GitHub/Gitea/Zapier/anything that POSTs JSON).

Modeled on OpenClaw `extensions/webhooks`: per-route shared secret, POST + JSON only,
size cap, timing-safe auth. Accepts either:
  - `Authorization: Bearer <secret>` / `x-openclaw-webhook-secret: <secret>`  (generic), or
  - `X-Hub-Signature-256: sha256=<hmac>`                                       (GitHub/Gitea)

The payload is normalized generically (text/message/goal/prompt, else the raw JSON).
Source-specific shaping (e.g. PR rendering) belongs to the caller or the agent's
system prompt — this stays a generic channel.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request

from src.domain.channels.base import (
    Channel,
    ChannelBinding,
    InboundMessage,
    verify_hmac_sha256,
    verify_shared_secret,
)

MAX_BODY_BYTES = 256 * 1024


class WebhookChannel(Channel):
    name = "webhook"

    def authenticate(
        self, binding: ChannelBinding, request: Request, raw_body: bytes
    ) -> bool:
        gh_sig = request.headers.get("x-hub-signature-256")
        if gh_sig is not None:
            return verify_hmac_sha256(binding.secret, raw_body, gh_sig)
        auth = request.headers.get("authorization", "")
        presented = (
            auth[len("Bearer ") :].strip() if auth.startswith("Bearer ") else None
        )
        presented = presented or request.headers.get("x-openclaw-webhook-secret")
        return verify_shared_secret(presented, binding.secret)

    def to_inbound(self, route_id: str, body: dict[str, Any]) -> InboundMessage:
        return InboundMessage(
            text=_render_text(body),
            channel=self.name,
            route_id=route_id,
            peer_id=route_id,
            sender_id="webhook",
            raw=body,
        )


def _render_text(body: dict[str, Any]) -> str:
    for key in ("text", "message", "goal", "prompt"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(body, indent=2)[:8000]
