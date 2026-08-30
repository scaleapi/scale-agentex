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

One live nonce per identity, enforced by a pointer key. A nonce is a bearer token:
whoever holds it gets linked to that provider identity by signing in as themselves.
So a user who mentions the agent repeatedly must not accumulate a handful of
separately-redeemable links — each is another chance for one to be clicked by the
wrong person, and consuming one does not invalidate its siblings. Repeat mentions
therefore reuse the live token (``create_or_reuse``) and re-send that same link,
capped by ``claim_send`` so the DMs stop while the link stays valid.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field, replace
from typing import Annotated, Any

from fastapi import Depends

from src.utils.logging import make_logger

logger = make_logger(__name__)

# Long enough for a human to switch windows and sign in, short enough that an
# abandoned link stops being interesting.
_TTL_S = 600

# 32 bytes of urlsafe randomness. Guessing is not a threat model at this size, but
# the token is still consumed on first use rather than relying on entropy alone.
_TOKEN_BYTES = 32

# How many times we will DM a user about the *same* pending link. Repeated mentions
# reuse the live nonce rather than minting another, so this caps DM noise without
# multiplying live tokens. Past the cap the caller should fall back to an ephemeral
# in-channel notice rather than going silent.
_MAX_SENDS = 2

_KEY_PREFIX = "link_nonce:"
# identity -> its one live token, so a second mention finds the first nonce instead
# of minting a parallel one. See create().
_USER_PREFIX = "link_nonce_user:"
# identity -> how many DMs we have sent about the live token.
_SEND_PREFIX = "link_nonce_sends:"


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


def _identity(provider: str, external_team_id: str, external_user_id: str) -> str:
    return f"{provider}:{external_team_id}:{external_user_id}"


def _user_key(provider: str, external_team_id: str, external_user_id: str) -> str:
    return f"{_USER_PREFIX}{_identity(provider, external_team_id, external_user_id)}"


def _send_key(provider: str, external_team_id: str, external_user_id: str) -> str:
    return f"{_SEND_PREFIX}{_identity(provider, external_team_id, external_user_id)}"


def _as_str(raw: Any) -> str | None:
    return (
        None if raw is None else (raw.decode() if isinstance(raw, bytes) else str(raw))
    )


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
        """Park a verified provider identity and return its opaque token.

        Invalidates any nonce this identity already holds, so one user never has two
        redeemable links at once. That matters because a nonce is a bearer token:
        every extra live one is another chance for a link to be redeemed by the
        wrong person, and consuming one would not invalidate its siblings.
        """
        client = self._redis()
        user_key = _user_key(
            request.provider, request.external_team_id, request.external_user_id
        )
        superseded = _as_str(await client.get(user_key))
        if superseded is not None:
            await client.delete(_key(superseded))

        token = secrets.token_urlsafe(_TOKEN_BYTES)
        await client.set(_key(token), json.dumps(asdict(request)), ex=_TTL_S)
        await client.set(user_key, token, ex=_TTL_S)
        # A genuinely new link gets a fresh send budget; the cap is per link, not
        # per user for all time.
        await client.delete(
            _send_key(
                request.provider, request.external_team_id, request.external_user_id
            )
        )
        logger.info(
            "link_nonce_created",
            extra={
                "provider": request.provider,
                "external_team_id": request.external_team_id,
                "external_user_id": request.external_user_id,
                "has_pending_turn": request.pending_turn is not None,
                "superseded_previous": superseded is not None,
                "ttl_s": _TTL_S,
            },
        )
        return token

    async def create_or_reuse(self, request: LinkRequest) -> tuple[str, bool]:
        """Return this identity's live token if it has one, else mint a fresh one.

        Returns ``(token, reused)``. Reuse deliberately does **not** extend the TTL:
        otherwise someone mentioning the agent every few minutes could keep a single
        token alive indefinitely, and the bounded lifetime is the point. The pending
        turn is refreshed within whatever window remains, so linking answers what
        the user most recently asked rather than their first attempt.
        """
        client = self._redis()
        token = _as_str(
            await client.get(
                _user_key(
                    request.provider,
                    request.external_team_id,
                    request.external_user_id,
                )
            )
        )
        if token is not None:
            live = await self.peek(token)
            # The pointer is keyed by identity so a match is expected; verified
            # anyway rather than trusting a stale pointer to name the right person.
            if live is not None and (
                live.provider,
                live.external_team_id,
                live.external_user_id,
            ) == (
                request.provider,
                request.external_team_id,
                request.external_user_id,
            ):
                await self._refresh_pending_turn(token, live, request.pending_turn)
                return token, True
        return await self.create(request), False

    async def claim_send(self, request: LinkRequest) -> bool:
        """Record intent to DM this user their link. False once the cap is reached.

        Counted per live link (the counter is cleared whenever a fresh nonce is
        minted), so a user stops being DMed about a link they are ignoring, while a
        genuinely new link is never silently withheld. On False the caller should
        still acknowledge in-channel — ephemerally — rather than appearing to do
        nothing.
        """
        key = _send_key(
            request.provider, request.external_team_id, request.external_user_id
        )
        client = self._redis()
        count = int(await client.incr(key))
        # Bound the counter to the life of the link it describes. The TTL re-check
        # covers a crash between INCR and EXPIRE, which would otherwise leave a key
        # with no expiry and a user permanently un-DMable.
        if count == 1 or int(await client.ttl(key)) < 0:
            await client.expire(key, _TTL_S)
        return count <= _MAX_SENDS

    async def _refresh_pending_turn(
        self, token: str, live: LinkRequest, pending_turn: dict[str, Any] | None
    ) -> None:
        """Point a reused nonce at the user's latest message, keeping its TTL.

        Best-effort: if the payload cannot be rewritten, the earlier question
        stands. That is worse UX than the newest one, but it is not wrong, and it
        is much better than dropping the nonce and forcing a re-link.
        """
        if pending_turn is None or pending_turn == live.pending_turn:
            return
        updated = replace(live, pending_turn=pending_turn)
        try:
            await self._redis().set(
                _key(token), json.dumps(asdict(updated)), keepttl=True
            )
        except Exception:  # noqa: BLE001 - no KEEPTTL: keep the older pending turn
            logger.warning(
                "[link_nonce] could not refresh pending turn; keeping the earlier one"
            )

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
