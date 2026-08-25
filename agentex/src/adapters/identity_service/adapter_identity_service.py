"""Mint SGP API keys via identity-service, acting as the user who asked.

Why this adapter exists at all: an event-driven turn has to act as the invoking
human to read that person's connected integrations, and the secrets service derives
the owner from the caller — there is no "fetch on behalf of" parameter. So the
gateway has to hold a credential belonging to that user, and this is where it comes
from.

Why identity-service and not egp-api-backend's ``/v5/api-keys``: there are two
independent API-key issuers on the platform and only one is accepted by the secrets
service.

    identity-service   POST /api-keys      -> ``ssk_is_<32 hex>``   ACCEPTED
    egp-api-backend    POST /v5/api-keys   -> ``sk_<...>``          401 at sgp-secrets

That was established empirically: a key minted from egp-api-backend for the correct
user, which authenticated fine against egp-api-backend itself, was rejected by
sgp-secrets with ``INVALID_API_KEY``. The discriminator is the issuer, not the
identity. Mint from the wrong one and everything looks right until the first secret
read fails.

Note the field names are camelCase here (``identityId``, ``identityType``,
``expiresOn``) — egp-api-backend's equivalent endpoint uses snake_case, so the two
are easy to confuse.

Auth: the caller's own credentials are forwarded, so the user mints their *own* key.
identity-service permits exactly that — ``assertCanManageTarget`` short-circuits on
"users may always manage their own keys" — with no admin role needed. We deliberately
do NOT hold a privileged key-minting credential: one that could mint for any user
would be strictly more dangerous than the per-user keys it would produce.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from src.utils.logging import make_logger

logger = make_logger(__name__)

# Read from the environment with no default on purpose. The address is
# deployment-specific and the service is cluster-internal (no public route), so a
# baked-in default would be wrong in most environments — and a *wrong* default here
# would POST a user's session credentials at whatever answers.
IDENTITY_SERVICE_URL_ENV = "IDENTITY_SERVICE_URL"

# Credential headers worth forwarding so identity-service sees the *user*. Mirrors
# what agentex-auth itself forwards, plus the bearer form the SGP UI uses when
# OneAuth is on. Nothing else is passed through — notably not cookies beyond the
# session ones, and never the gateway's own bot key.
_FORWARDABLE = ("cookie", "authorization", "x-api-key", "x-selected-account-id")

_TIMEOUT_S = float(os.getenv("IDENTITY_SERVICE_TIMEOUT_S", "15"))


class IdentityServiceError(RuntimeError):
    """A key could not be minted. Carries a user-safe reason."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def base_url() -> str:
    """Identity-service base URL from the environment.

    Raises rather than falling back, because the alternative is sending a user's
    forwarded session credentials to an unintended host.
    """
    raw = os.getenv(IDENTITY_SERVICE_URL_ENV, "").strip()
    if not raw:
        raise IdentityServiceError(
            f"{IDENTITY_SERVICE_URL_ENV} is not configured on this deployment."
        )
    return raw.rstrip("/")


def forwardable_headers(headers: dict[str, str]) -> dict[str, str]:
    """The subset of an inbound request's headers that identify the caller."""
    lowered = {k.lower(): v for k, v in headers.items()}
    return {k: lowered[k] for k in _FORWARDABLE if lowered.get(k)}


class IdentityServiceClient:
    """Thin client. Only the one operation the link flow needs."""

    def __init__(self, url: str | None = None):
        self.url = (url or base_url()).rstrip("/")

    async def mint_user_api_key(
        self,
        *,
        sgp_user_id: str,
        name: str,
        auth_headers: dict[str, str],
        expires_on: datetime | None = None,
    ) -> tuple[str, datetime | None]:
        """Mint an ``ssk_is_`` key owned by ``sgp_user_id``.

        ``auth_headers`` must authenticate AS that user — the caller's own session
        from the link callback. Returns ``(secret, expires_on)``; the secret is
        returned exactly once by identity-service and is never retrievable again,
        so the caller must persist it before doing anything else that can fail.

        ``expires_on`` bounds the credential. Strongly recommended: the stored key
        is the most sensitive thing agentex holds, and an expiry converts "valid
        until someone notices" into a known window.
        """
        if not sgp_user_id:
            raise IdentityServiceError("cannot mint a key without a user id")
        payload: dict[str, Any] = {
            "name": name,
            "identityId": sgp_user_id,
            "identityType": "user",
        }
        if expires_on is not None:
            # NestJS class-validator @IsDate with a transform accepts ISO-8601.
            payload["expiresOn"] = expires_on.isoformat()

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(
                    f"{self.url}/api-keys",
                    json=payload,
                    headers={**auth_headers, "content-type": "application/json"},
                )
        except Exception as exc:  # noqa: BLE001 - network/DNS; surfaced to the user
            logger.warning("[identity-service] mint request failed", exc_info=True)
            raise IdentityServiceError(
                "Couldn't reach the identity service to create a key."
            ) from exc

        if resp.status_code in (401, 403):
            # The session didn't carry through, or it isn't this user's own key.
            raise IdentityServiceError(
                "Your session wasn't accepted when creating the key. "
                "Sign in to SGP and try the link again.",
                status=resp.status_code,
            )
        if resp.status_code >= 400:
            detail = (resp.text or "")[:200]
            logger.warning(
                "[identity-service] mint failed (%s): %s", resp.status_code, detail
            )
            raise IdentityServiceError(
                f"The identity service rejected the request (HTTP {resp.status_code}).",
                status=resp.status_code,
            )

        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise IdentityServiceError(
                "Unreadable response from identity service."
            ) from exc

        secret = body.get("secret")
        if not secret:
            # The secret is only present on create/rotate. Its absence means we got
            # a record back but no usable credential — nothing to store.
            raise IdentityServiceError(
                "The identity service created a key but returned no secret."
            )
        if not str(secret).startswith("ssk_"):
            # Guards against the wrong-issuer mistake this module exists to avoid:
            # a non-ssk_ key will authenticate elsewhere but 401 at sgp-secrets, and
            # failing here is far cheaper than debugging that later.
            raise IdentityServiceError(
                "The identity service returned an unexpected key format; refusing "
                "to store a credential the secrets service won't accept."
            )

        returned_expiry = body.get("expiresOn")
        parsed_expiry: datetime | None = expires_on
        if isinstance(returned_expiry, str):
            try:
                parsed_expiry = datetime.fromisoformat(
                    returned_expiry.replace("Z", "+00:00")
                )
            except ValueError:
                pass  # keep what we requested

        logger.info(
            "identity_service_key_minted",
            extra={
                "sgp_user_id": sgp_user_id,
                "key_id": body.get("id"),
                "expires_on": str(parsed_expiry),
            },
        )
        return str(secret), parsed_expiry
