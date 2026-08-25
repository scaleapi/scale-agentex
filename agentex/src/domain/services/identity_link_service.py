"""Resolve a provider identity to the SGP identity an event-driven turn should act as.

Two lookups with deliberately different caching, because they carry different things:

``resolve()``          -> the link (who this Slack user is). Cached in Redis. The
                          entity holds no credential, so the cache holds no secret.
``acting_headers()``   -> the delegation headers, including that user's SGP API key.
                          NEVER cached. Read from Postgres per turn, decrypted in
                          memory, handed straight to the ACP call. One indexed
                          lookup is cheap; a key sitting in Redis is not.

Negative results are cached too. Unlinked users are the common case during rollout,
and without a negative entry every event from one is a guaranteed miss plus a DB
round trip — exactly the traffic a busy shared channel produces. Negatives get a
shorter TTL so a freshly linked user starts working promptly.

Deliberately NOT fail-open: a cache miss falls through to Postgres, but a *lookup
failure* propagates. "We could not determine who this is" must never collapse into
"this is nobody", because the caller treats the latter as "run as the shared bot"
and would silently downgrade a user-scoped turn.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends

from src.domain.entities.identity_links import IdentityLinkEntity, IdentityProvider
from src.domain.repositories.identity_link_repository import DIdentityLinkRepository
from src.utils.credential_encryption import CredentialEncryptionError
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Positive entries are stable — a link changes only on an explicit link/unlink, and
# both paths invalidate. Negatives expire fast so linking feels immediate.
_CACHE_TTL_S = int(os.getenv("IDENTITY_LINK_CACHE_TTL", "300"))
_NEGATIVE_CACHE_TTL_S = int(os.getenv("IDENTITY_LINK_NEGATIVE_CACHE_TTL", "30"))

# Distinguishes "cached: known to be unlinked" from "not in cache".
_UNLINKED = "-"

HEADER_API_KEY = "x-api-key"
HEADER_SELECTED_ACCOUNT_ID = "x-selected-account-id"


def _cache_key(
    provider: IdentityProvider, external_team_id: str, external_user_id: str
) -> str:
    return f"identity_link:{provider.value}:{external_team_id}:{external_user_id}"


class ResolvedIdentity:
    """A provider identity resolved to an SGP identity.

    ``principal`` is shaped for agentex-auth's ``SGPPrincipalContext`` and is passed
    to ``/v1/authz/*`` verbatim. It carries no api_key because permission checks
    only need (user_id, account_id) — the credential travels separately, on the
    delegation headers, and only when the caller asks for it.
    """

    def __init__(self, link: IdentityLinkEntity):
        self.link = link
        self.sgp_user_id = link.sgp_user_id
        self.sgp_account_id = link.sgp_account_id

    @property
    def principal(self) -> dict[str, Any]:
        return {"user_id": self.sgp_user_id, "account_id": self.sgp_account_id}

    def credential_is_usable(self, *, now: datetime | None = None) -> bool:
        return self.link.credential_is_usable(now=now or datetime.now(UTC))


class IdentityLinkService:
    def __init__(self, repository: DIdentityLinkRepository):
        self.repository = repository

    async def resolve(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
    ) -> ResolvedIdentity | None:
        """Resolve a provider identity, or None when it isn't linked.

        None means "definitively not linked". A lookup failure raises.
        """
        if not (external_team_id and external_user_id):
            return None

        cached = await self._cache_get(provider, external_team_id, external_user_id)
        if cached is _UNLINKED:
            return None
        if cached is not None:
            return ResolvedIdentity(cached)

        link = await self.repository.get_active_by_external_user(
            provider=provider,
            external_team_id=external_team_id,
            external_user_id=external_user_id,
        )
        await self._cache_put(provider, external_team_id, external_user_id, link)
        return ResolvedIdentity(link) if link else None

    async def acting_headers(self, identity: ResolvedIdentity) -> dict[str, str] | None:
        """The delegation headers for acting as this user, or None if we can't.

        These are what ``build_delegation_headers`` converts into
        ``x-acting-user-api-key`` on the ACP call, which is what makes the agent's
        user-scoped tools (Notion, Linear, Slack) resolve *this user's* connections
        instead of the gateway bot's.

        Returns None — never raises — for every "can't act as them" case: no stored
        credential, an expired one, or a ciphertext that won't decrypt. The caller
        decides what to do about it (fall back, or prompt a re-link), and a
        None-vs-exception split would make that awkward at the call site. The reason
        is logged, since the three cases need different fixes.
        """
        if not identity.link.has_credential:
            logger.info(
                "identity_link_no_credential",
                extra={"sgp_user_id": identity.sgp_user_id},
            )
            return None
        if not identity.credential_is_usable():
            logger.info(
                "identity_link_credential_expired",
                extra={
                    "sgp_user_id": identity.sgp_user_id,
                    "expired_at": str(identity.link.credential_expires_at),
                },
            )
            return None
        try:
            credential = await self.repository.get_credential(identity.link.id)
        except CredentialEncryptionError:
            # Wrong key or tampered ciphertext. Not recoverable here; the owner has
            # to re-link. Logged loudly because it usually means a key rotation
            # left existing rows unreadable.
            logger.warning(
                "identity_link_credential_unreadable",
                extra={"sgp_user_id": identity.sgp_user_id},
                exc_info=True,
            )
            return None
        if not credential:
            return None
        headers = {HEADER_API_KEY: credential}
        if identity.sgp_account_id:
            headers[HEADER_SELECTED_ACCOUNT_ID] = identity.sgp_account_id
        return headers

    async def invalidate(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
    ) -> None:
        """Drop the cached entry, so a link/unlink takes effect on the next event
        rather than after the TTL."""
        client = self._redis()
        if client is None:
            return
        try:
            await client.delete(
                _cache_key(provider, external_team_id, external_user_id)
            )
        except Exception:  # noqa: BLE001 - invalidation is best-effort
            logger.warning("[identity_link] cache invalidation failed", exc_info=True)

    # ----------------------------------------------------------------- cache layer

    def _redis(self):
        """The shared Redis client, or None when unavailable (unit tests, deps not
        loaded). A missing cache degrades to DB-only, never to a wrong answer."""
        try:
            from src.config.dependencies import GlobalDependencies

            pool = GlobalDependencies().redis_pool
        except Exception:  # noqa: BLE001 - deps not initialized -> no cache
            return None
        if pool is None:
            return None
        try:
            import redis.asyncio as redis

            return redis.Redis(connection_pool=pool)
        except Exception:  # noqa: BLE001
            return None

    async def _cache_get(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
    ) -> IdentityLinkEntity | str | None:
        """Entity on a hit, ``_UNLINKED`` on a cached negative, None for a miss
        (including any cache failure)."""
        client = self._redis()
        if client is None:
            return None
        try:
            raw = await client.get(
                _cache_key(provider, external_team_id, external_user_id)
            )
        except Exception:  # noqa: BLE001 - a cache error is just a miss
            logger.warning("[identity_link] cache read failed", exc_info=True)
            return None
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        if raw == _UNLINKED:
            return _UNLINKED
        try:
            return IdentityLinkEntity.model_validate(json.loads(raw))
        except Exception:  # noqa: BLE001 - stale/incompatible payload -> re-read DB
            logger.warning("[identity_link] cache payload unusable", exc_info=True)
            return None

    async def _cache_put(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
        link: IdentityLinkEntity | None,
    ) -> None:
        client = self._redis()
        if client is None:
            return
        key = _cache_key(provider, external_team_id, external_user_id)
        try:
            if link is None:
                await client.set(key, _UNLINKED, ex=_NEGATIVE_CACHE_TTL_S)
            else:
                # Safe to cache: IdentityLinkEntity has no credential field, so this
                # payload cannot contain key material.
                await client.set(key, link.model_dump_json(), ex=_CACHE_TTL_S)
        except Exception:  # noqa: BLE001 - caching is best-effort
            logger.warning("[identity_link] cache write failed", exc_info=True)


DIdentityLinkService = Annotated[IdentityLinkService, Depends(IdentityLinkService)]
