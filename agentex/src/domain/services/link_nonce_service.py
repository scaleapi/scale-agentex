"""Short-lived handshake state for the identity-link flow.

The link flow spans two HTTP requests that each prove one half of an identity:

  1. A Slack event or slash command. Slack's HMAC proves the *provider* identity —
     we know this really is ``U…`` in team ``T…``, because only Slack could have
     signed it.
  2. A browser hit on an authenticated agentex route. The session proves the *SGP*
     identity.

Nothing carries between them on its own, so the first proof has to be parked
somewhere the second request can pick it up. This is that parking spot.

Why a server-side nonce rather than putting the Slack ids in the link URL: a URL is
user-editable. Given ``?slack_user=<someone else>``, an attacker could click their
own link while signed in as themselves and bind *your* Slack identity to *their* SGP
account — after which your Slack messages would run as them, using their
integrations, with the resulting task (and your prompt) landing in their account.
Handing out an opaque token instead means nothing in the URL is meaningful, so
nothing in it is forgeable.

Signed URL parameters would also close that hole, and would need no Redis. They are
rejected here for two reasons: a signed URL is replayable for its whole validity
window, whereas a nonce is consumed on first use; and the pending turn (so the user
gets an answer to the question they originally asked) does not fit in a query string.

The nonce holds no secrets — only public-ish identifiers and the user's own message
— so its blast radius if Redis were read is "someone learns a Slack user id". The
credential it eventually produces is never stored here.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any

from fastapi import Depends

from src.utils.logging import make_logger

logger = make_logger(__name__)

# Long enough for a human to switch windows and sign in, short enough that an
# abandoned link stops being interesting.
_TTL_S = int(os.getenv("IDENTITY_LINK_NONCE_TTL", "600"))

# 32 bytes of urlsafe randomness. Guessing is not a threat model at this size, but
# the token is still consumed on first use rather than relying on entropy alone.
_TOKEN_BYTES = 32

_KEY_PREFIX = "link_nonce:"


@dataclass
class LinkRequest:
    """The verified provider identity, parked for the browser leg of the flow."""

    provider: str
    external_team_id: str
    external_user_id: str
    # For the confirmation screen. Naming both sides is what makes a mis-clicked
    # link visible to the person clicking it, so this is a security affordance
    # rather than decoration.
    display_name: str = ""
    # The turn that triggered the prompt, so linking can end with an answer to the
    # original question instead of "now ask me again".
    pending_turn: dict[str, Any] | None = field(default=None)


def _key(token: str) -> str:
    return f"{_KEY_PREFIX}{token}"


class LinkNonceService:
    """Create / read / consume link nonces.

    Requires Redis. Unlike the identity-link cache — where a missing cache just
    means "read the database" — there is no fallback here: without somewhere to
    park the Slack identity, the flow cannot be completed safely, and the
    alternative (trusting ids from the URL) is the vulnerability described above.
    So a missing Redis raises rather than degrading.
    """

    def __init__(self, redis_client: Any | None = None):
        self._client = redis_client

    def _redis(self):
        if self._client is not None:
            return self._client
        from src.config.dependencies import GlobalDependencies

        pool = GlobalDependencies().redis_pool
        if pool is None:
            raise RuntimeError(
                "identity linking requires Redis (nonce storage) and no pool is "
                "configured"
            )
        import redis.asyncio as redis

        self._client = redis.Redis(connection_pool=pool)
        return self._client

    async def create(self, request: LinkRequest) -> str:
        """Park a verified provider identity and return its opaque token."""
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        await self._redis().set(_key(token), json.dumps(asdict(request)), ex=_TTL_S)
        logger.info(
            "link_nonce_created",
            extra={
                "provider": request.provider,
                "external_team_id": request.external_team_id,
                "external_user_id": request.external_user_id,
                "has_pending_turn": request.pending_turn is not None,
                "ttl_s": _TTL_S,
            },
        )
        return token

    async def peek(self, token: str) -> LinkRequest | None:
        """Read without consuming — for rendering the confirmation screen.

        Deliberately separate from ``consume``: if loading the page burned the
        nonce, a refresh (or a browser prefetching the link) would break the flow
        before the user could confirm.
        """
        if not token:
            return None
        raw = await self._redis().get(_key(token))
        return self._decode(raw)

    async def consume(self, token: str) -> LinkRequest | None:
        """Read and delete atomically — single use, on confirm.

        ``GETDEL`` so two concurrent confirms can't both succeed. Falls back to
        GET+DELETE on Redis older than 6.2, which is very slightly racy but only
        between two requests already holding the same token.
        """
        if not token:
            return None
        client = self._redis()
        try:
            raw = await client.getdel(_key(token))
        except Exception:  # noqa: BLE001 - GETDEL unsupported on older Redis
            raw = await client.get(_key(token))
            if raw is not None:
                await client.delete(_key(token))
        return self._decode(raw)

    @staticmethod
    def _decode(raw: Any) -> LinkRequest | None:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            data = json.loads(raw)
            return LinkRequest(**data)
        except Exception:  # noqa: BLE001 - a malformed nonce is an expired nonce
            logger.warning("[link_nonce] undecodable payload; treating as expired")
            return None


DLinkNonceService = Annotated[LinkNonceService, Depends(LinkNonceService)]
