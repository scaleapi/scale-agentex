"""Identity-link routes — the browser leg of connecting a Slack user to SGP.

These routes deliberately live under ``/integrations`` and NOT under ``/slack``.
``/slack`` is auth-whitelisted (Slack's signature is its auth), so a callback placed
there would run unauthenticated — which would defeat the entire mechanism, since the
whole point of this leg is to learn who the caller is in SGP from their own session.

The flow:

    GET  /integrations/slack/link?nonce=…    confirmation screen (does not consume)
    POST /integrations/slack/link            confirm -> mint -> store

By the time the POST runs, both halves of the identity are present in one request:
the Slack side from the nonce (parked when Slack's HMAC verified the event), the SGP
side from the authenticated session. That coincidence is the only moment the mapping
can be established safely.

Rendered as plain HTML rather than JSON: the user arrives here by clicking a link in
Slack, so the response is for a human, and the confirmation step is a security
control — naming both identities is what makes a mis-clicked link visible.
"""

from __future__ import annotations

import html
import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from src.adapters.identity_service.adapter_identity_service import (
    IdentityServiceClient,
    IdentityServiceError,
    forwardable_headers,
)
from src.api.middleware_utils import get_request_headers_to_forward
from src.config.dependencies import (
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
)
from src.domain.entities.identity_links import IdentityLinkMethod, IdentityProvider
from src.domain.repositories.identity_link_repository import IdentityLinkRepository
from src.domain.services.identity_link_service import IdentityLinkService
from src.domain.services.link_nonce_service import LinkNonceService
from src.utils.credential_encryption import CredentialEncryptionError
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])

# How long a minted key lasts. Bounded on purpose: this is the most sensitive thing
# agentex stores, and an expiry turns "valid until someone notices" into a known
# window. Long enough that re-linking isn't a weekly chore.
_KEY_TTL_DAYS = int(os.getenv("IDENTITY_LINK_KEY_TTL_DAYS", "30"))

_KEY_NAME_PREFIX = "agentex-slack-link"


def _page(title: str, body: str, *, status: int = 200) -> HTMLResponse:
    """Minimal self-contained page. No external assets — this renders inside
    whatever browser Slack opened, possibly without network access to our CDN."""
    return HTMLResponse(
        status_code=status,
        content=(
            "<!doctype html><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title>"
            "<style>"
            "body{font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "max-width:34rem;margin:4rem auto;padding:0 1.25rem;color:#1d1d1f}"
            "h1{font-size:1.3rem;margin:0 0 1rem}"
            "dl{background:#f5f5f7;border-radius:10px;padding:1rem 1.25rem;margin:1.25rem 0}"
            "dt{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:#6e6e73}"
            "dd{margin:.15rem 0 .9rem;font-weight:600}dd:last-child{margin-bottom:0}"
            "button{font:inherit;font-weight:600;background:#0b6bcb;color:#fff;border:0;"
            "border-radius:8px;padding:.6rem 1.1rem;cursor:pointer}"
            ".muted{color:#6e6e73;font-size:.9rem}"
            "</style>"
            f"{body}"
        ),
    )


def _identity_link_service() -> IdentityLinkService:
    engine = database_async_read_write_engine()
    return IdentityLinkService(
        IdentityLinkRepository(
            database_async_read_write_session_maker(engine),
            database_async_read_only_session_maker(engine),
        )
    )


def _principal(request: Request) -> tuple[str | None, str | None, str | None]:
    """(sgp_user_id, sgp_account_id, email) from the authenticated session.

    Populated by AgentexAuthMiddleware, which is why this route must not be
    whitelisted. With authz disabled locally there is no principal, so linking is
    refused rather than guessed at — binding an identity is exactly the operation
    that must not proceed on an assumption.
    """
    ctx = getattr(request.state, "principal_context", None) or {}
    if not isinstance(ctx, dict):
        ctx = getattr(ctx, "__dict__", {}) or {}
    raw_user = ctx.get("raw_user") or {}
    return (
        ctx.get("user_id"),
        ctx.get("account_id"),
        raw_user.get("email") if isinstance(raw_user, dict) else None,
    )


@router.get("/slack/link", summary="Confirm linking a Slack identity to SGP")
async def slack_link_page(request: Request, nonce: str = "") -> HTMLResponse:
    """Render the confirmation screen. Does NOT consume the nonce, so a refresh or
    a link-prefetching browser doesn't break the flow."""
    link_request = await LinkNonceService().peek(nonce)
    if link_request is None:
        return _page(
            "Link expired",
            "<h1>This link has expired</h1><p class=muted>Links are single-use and "
            "valid for a few minutes. Mention the agent in Slack again to get a "
            "fresh one.</p>",
            status=400,
        )

    sgp_user_id, _account_id, email = _principal(request)
    if not sgp_user_id:
        return _page(
            "Sign in required",
            "<h1>Please sign in to SGP</h1><p class=muted>Sign in and open this "
            "link again to finish connecting your account.</p>",
            status=401,
        )

    slack_who = link_request.display_name or link_request.external_user_id
    return _page(
        "Connect your account",
        "<h1>Connect your Slack account?</h1>"
        "<p>This lets the agent use <strong>your</strong> connected tools "
        "(Notion, Linear, …) when you ask it something in Slack.</p>"
        "<dl>"
        f"<dt>Slack</dt><dd>{html.escape(slack_who)}</dd>"
        f"<dt>SGP</dt><dd>{html.escape(email or sgp_user_id)}</dd>"
        "</dl>"
        "<form method=post>"
        f"<input type=hidden name=nonce value='{html.escape(nonce)}'>"
        "<button type=submit>Connect</button></form>"
        "<p class=muted style='margin-top:1.5rem'>If either name above isn't you, "
        "close this page and don't continue.</p>",
    )


@router.post("/slack/link", summary="Complete a Slack identity link")
async def slack_link_confirm(request: Request, nonce: str = Form("")) -> HTMLResponse:
    """Mint a key as the signed-in user and store the mapping.

    Order matters: the nonce is consumed only after a successful mint, so a
    transient identity-service failure leaves the link clickable instead of
    burning it and forcing the user back to Slack.
    """
    link_request = await LinkNonceService().peek(nonce)
    if link_request is None:
        return _page(
            "Link expired",
            "<h1>This link has expired</h1><p class=muted>Mention the agent in "
            "Slack again to get a fresh one.</p>",
            status=400,
        )

    sgp_user_id, sgp_account_id, email = _principal(request)
    if not sgp_user_id:
        return _page(
            "Sign in required",
            "<h1>Please sign in to SGP</h1>",
            status=401,
        )

    provider = IdentityProvider(link_request.provider)
    service = _identity_link_service()

    # Report a conflict before the partial unique index does, so the user sees a
    # sentence instead of an integrity error.
    existing = await service.repository.get_active_by_sgp_user(
        provider=provider,
        external_team_id=link_request.external_team_id,
        sgp_user_id=sgp_user_id,
    )
    if existing and existing.external_user_id != link_request.external_user_id:
        return _page(
            "Already linked",
            "<h1>That SGP account is already linked</h1>"
            "<p class=muted>It's connected to a different Slack user in this "
            "workspace. Disconnect that one first.</p>",
            status=409,
        )

    expires_on = datetime.now(UTC) + timedelta(days=_KEY_TTL_DAYS)
    try:
        secret, actual_expiry = await IdentityServiceClient().mint_user_api_key(
            sgp_user_id=sgp_user_id,
            name=f"{_KEY_NAME_PREFIX}-{link_request.external_user_id}",
            auth_headers=forwardable_headers(get_request_headers_to_forward(request)),
            expires_on=expires_on,
        )
    except IdentityServiceError as exc:
        logger.warning("identity link mint failed: %s", exc)
        return _page(
            "Couldn't create a key",
            f"<h1>Couldn't finish connecting</h1><p>{html.escape(str(exc))}</p>"
            "<p class=muted>Your link is still valid — you can retry.</p>",
            status=502,
        )

    try:
        await service.repository.upsert_link(
            provider=provider,
            external_team_id=link_request.external_team_id,
            external_user_id=link_request.external_user_id,
            sgp_user_id=sgp_user_id,
            sgp_account_id=sgp_account_id or "",
            linked_via=IdentityLinkMethod.EXPLICIT,
            credential=secret,
            credential_expires_at=actual_expiry,
        )
    except CredentialEncryptionError:
        # AGENTEX_CREDENTIAL_ENCRYPTION_KEY is missing or malformed, so the freshly
        # minted key cannot be stored safely. Deliberately NOT stored in plaintext.
        # Reported as an operator problem rather than a 500, because the user can't
        # do anything about it and would otherwise just retry forever. The nonce is
        # left intact so the link still works once the key is configured.
        logger.error(
            "identity link failed: credential encryption is not configured; "
            "set AGENTEX_CREDENTIAL_ENCRYPTION_KEY",
            exc_info=True,
        )
        return _page(
            "Not configured",
            "<h1>Couldn't finish connecting</h1>"
            "<p>This deployment isn't set up to store credentials yet.</p>"
            "<p class=muted>Nothing was saved. Please let the team know — the "
            "server needs its credential encryption key configured.</p>",
            status=503,
        )
    # Burn the nonce only now that the link is durable.
    await LinkNonceService().consume(nonce)
    # Drop the negative cache entry so the very next Slack message resolves.
    await service.invalidate(
        provider=provider,
        external_team_id=link_request.external_team_id,
        external_user_id=link_request.external_user_id,
    )
    logger.info(
        "identity_link_completed",
        extra={
            "provider": provider.value,
            "external_user_id": link_request.external_user_id,
            "sgp_user_id": sgp_user_id,
            "expires_on": str(actual_expiry),
        },
    )

    when = actual_expiry.date().isoformat() if actual_expiry else "further notice"
    return _page(
        "Connected",
        "<h1>You're connected</h1>"
        f"<p>The agent will now use your own tools when you ask it something in "
        f"Slack, as <strong>{html.escape(email or sgp_user_id)}</strong>.</p>"
        f"<p class=muted>This connection is valid until {html.escape(when)}, after "
        "which the agent will ask you to reconnect. You can close this page and go "
        "back to Slack.</p>",
    )
