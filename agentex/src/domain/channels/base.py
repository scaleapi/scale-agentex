"""Channel abstraction: normalize any external surface (webhook, Slack, …) into one
inbound shape, and drive an agent turn from it.

Modeled on OpenClaw's channel plugins (github.com/openclaw/openclaw,
`src/channels/**`) and the claw0 tutorial: every platform produces the same
`InboundMessage`; the agent-driving core is channel-agnostic. A new channel
(Slack, etc.) implements `Channel` — `authenticate` + `to_inbound` for ingress,
and (when it needs to push replies) its own outbound — without touching the router.
"""

from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from starlette.requests import Request


@dataclass
class InboundMessage:
    """Normalized inbound event. Every channel produces this; the router only sees this."""

    text: str
    channel: str  # "webhook" | "slack" | …
    route_id: str = ""  # which binding received it (webhook route / slack team)
    peer_id: str = ""  # conversation scope: DM user, channel:thread, route_id, …
    sender_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def session_key(self, agent_name: str) -> str:
        """Stable per-conversation key → reused as the agentex task name (get-or-create)."""
        basis = self.peer_id or self.route_id or "main"
        digest = hashlib.sha1(
            f"{agent_name}:{self.channel}:{basis}".encode()
        ).hexdigest()[:16]
        return f"ch-{self.channel}-{digest}"


@dataclass
class ChannelBinding:
    """A route's binding to one agent.

    A binding provides the turn's task params one of two ways:

    - **inline** (`params` set): the params are given directly — a one-off with no
      remote lookup.
    - **remote** (`params_source` set): a URL the channel GETs at dispatch time to
      obtain the params (see `domain.channels.params_source`). The source endpoint
      owns whatever produces those params; the channel layer just forwards the result
      and never interprets it.

    `params` is an OPAQUE dict forwarded verbatim as the task/create params — the
    agentex platform does not interpret it. Whatever a given agent expects there
    (system prompt, tools, model, …) is that agent's concern, not the channel layer's.
    """

    secret: str
    agent_name: str
    # Which channel implementation handles this route (registry key, e.g. "webhook",
    # "github_pr", "slack"). Defaults to the generic webhook channel.
    channel: str = "webhook"
    params: dict[str, Any] = field(default_factory=dict)
    # When set, `params` is fetched from this URL at dispatch time (the source owns
    # what they contain; the channel layer just forwards them).
    params_source: str | None = None
    # Extra metadata to stamp on the task (e.g. returned alongside remote params).
    extra_task_metadata: dict[str, str] = field(default_factory=dict)
    # Headers the router forwards to the agent (auth/delegation). Empty for local/open.
    forward_headers: dict[str, str] = field(default_factory=dict)


def verify_shared_secret(presented: str | None, secret: str) -> bool:
    """Timing-safe shared-secret check (OpenClaw `safeEqualSecret`)."""
    if not presented or not secret:
        return False
    return hmac.compare_digest(presented, secret)


def verify_hmac_sha256(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify an `sha256=<hex>` HMAC signature (GitHub/Gitea-style)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


class Channel(ABC):
    """One external surface, modeled on OpenClaw's channel plugin facets.

    Ingress (required): `authenticate` + `to_inbound` (normalize an inbound event).
    Outbound (optional): `deliver` + `chunk` — OpenClaw's `ChannelOutboundAdapter`
    (`deliver` + `chunker`/`textChunkLimit`). Interactive channels that push replies
    (Slack -> chat.postMessage) set `supports_outbound = True` and implement `deliver`.
    A plain webhook leaves it unset — its reply is the HTTP response, so the caller
    returns the reply rather than pushing it. `deliver_reply()` (below) is OpenClaw's
    buffered dispatcher: it chunks the agent reply and calls `deliver` per block.
    """

    name: str = "unknown"
    supports_outbound: bool = False
    # Platform message size limit for chunking (OpenClaw textChunkLimit). None = no split.
    text_chunk_limit: int | None = None

    @abstractmethod
    def authenticate(
        self, binding: ChannelBinding, request: Request, raw_body: bytes
    ) -> bool:
        """Return True iff the request is authentic for this binding."""

    @abstractmethod
    def to_inbound(self, route_id: str, body: dict[str, Any]) -> InboundMessage:
        """Normalize the parsed JSON payload into an InboundMessage."""

    async def deliver(self, peer_id: str, text: str) -> None:
        """Send one (already-chunked) reply block to conversation `peer_id`.

        Default: unsupported. Push channels override this (and set supports_outbound).
        """
        raise NotImplementedError(f"channel {self.name!r} has no outbound deliver()")

    def chunk(self, text: str) -> list[str]:
        """Split a reply to `text_chunk_limit`, preferring paragraph boundaries
        (OpenClaw's chunker, markdown-agnostic default)."""
        limit = self.text_chunk_limit
        if not limit or len(text) <= limit:
            return [text]
        out: list[str] = []
        cur = ""
        for para in text.split("\n\n"):
            if cur and len(cur) + len(para) + 2 > limit:
                out.append(cur)
                cur = ""
            cur = f"{cur}\n\n{para}" if cur else para
        if cur:
            out.append(cur)
        return out or [text[:limit]]


async def deliver_reply(channel: Channel, peer_id: str, text: str) -> None:
    """Buffered reply dispatcher (OpenClaw dispatchReplyWithBufferedBlockDispatcher):
    chunk the agent reply and deliver each block through the channel's outbound."""
    for block in channel.chunk(text):
        if block.strip():
            await channel.deliver(peer_id, block)
