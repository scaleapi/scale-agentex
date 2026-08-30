"""Identity-link routes — the browser leg of connecting a Slack user to SGP.

These routes deliberately live under ``/integrations`` and NOT under ``/slack``.
``/slack`` is auth-whitelisted (Slack's signature is its auth), so a callback placed
there would run unauthenticated — which would defeat the entire mechanism, since the
whole point of this leg is to learn who the caller is in SGP from their own session.

The flow:

    GET  /integrations/slack/link?nonce=…    confirmation screen (does not consume)
    POST /integrations/slack/link            confirm -> store the caller's session

By the time the POST runs, both halves of the identity are present in one request:
the Slack side from the nonce (parked when Slack's HMAC verified the event), the SGP
side from the authenticated session. That coincidence is the only moment the mapping
can be established safely.

The credential we keep is the caller's **own session cookie**, not a freshly minted
API key. Minting was the original design and it does not work: identity-service
permits one API key per user and every active user already has one, so ``POST
/api-keys`` answers 409 ("API key already exists for this user") and the secret of
the existing key cannot be read back. Rotating theirs would silently break whatever
else uses it.

The session cookie avoids all of that, and is a better credential besides. It is
already in this request, so there is no outbound call to fail; it carries its own
expiry in the JWT, where a minted key defaults to none; taking it changes nothing
about the user's existing credentials; and the secrets service accepts it directly
(verified: a session cookie plus ``x-selected-account-id`` authenticates, while the
cookie alone is refused for want of account context).

The tradeoff is that the link now lives and dies with the session: sign-out or
revocation ends it, which surfaces downstream as a rejected credential and should
prompt a re-link rather than an error.

Rendered as plain HTML rather than JSON: the user arrives here by clicking a link in
Slack, so the response is for a human, and the confirmation step is a security
control — naming both identities is what makes a mis-clicked link visible.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from src.config.dependencies import (
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
)
from src.domain.entities.identity_links import IdentityLinkMethod, IdentityProvider
from src.domain.repositories.identity_link_repository import IdentityLinkRepository
from src.domain.services.identity_link_service import (
    IdentityLinkService,
    session_cookie_name,
)
from src.domain.services.link_nonce_service import LinkNonceService
from src.utils import session_jwt
from src.utils.credential_encryption import CredentialEncryptionError
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])

# Used only when the session token doesn't declare its own expiry. Never "no
# expiry": storing a credential with an unbounded lifetime is how you end up
# holding one indefinitely, so an unknown expiry becomes a short known one.
_FALLBACK_TTL_DAYS = 30

# Email matching has no flag: it enforces itself whenever Slack will tell us the
# email, and stands down when it won't. See ``_email_mismatch``.


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


def _session_credential(request: Request) -> str | None:
    """The caller's session cookie value, or None if it isn't on the request.

    Parsed by splitting on ``;`` rather than with ``http.cookies``: a real browser
    sends a long Cookie header full of analytics morsels that the stdlib parser
    chokes on, silently dropping every morsel after the first bad one — which can
    include the session cookie itself. The same reasoning (and the same approach)
    applies in ``delegation_headers``.

    The name comes from the delegation allowlist, so what we store here is by
    construction what the delegation layer will forward later. None when cookie
    delegation is disabled: there would be no way to act through the credential, so
    there is no point storing one.
    """
    wanted = session_cookie_name()
    if wanted is None:
        return None
    raw = request.headers.get("cookie") or ""
    for part in raw.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.strip() == wanted:
            return value.strip() or None
    return None


async def _email_mismatch(external_user_id: str, sgp_email: str | None) -> bool:
    """True when Slack and SGP demonstrably identify different people.

    This is the only real defence against a *forwarded* link. The nonce stops an
    attacker forging someone else's Slack identity; it does not stop them sending
    their OWN link to a victim, who — clicking it while signed in — would bind the
    attacker's Slack identity to their SGP account, after which the attacker's Slack
    messages run as them with their integrations.

    **Self-enabling, with no flag.** The check needs the ``users:read.email`` Slack
    scope, which may not be granted. Rather than gate that on configuration — where
    the flag and the scope must be flipped together, and flipping one alone either
    breaks every link or silently protects nothing — it simply enforces whenever
    Slack answers with an email and stands down when it won't. Granting the scope
    turns the protection on by itself.

    So the asymmetry is deliberate: **verified different -> refuse; unverifiable ->
    allow and warn.** Failing closed on an unreadable email would be stronger, but
    with no flag to distinguish "scope missing" from "Slack had a bad minute" it
    would make linking fail randomly. The gap it leaves is not attacker-reachable:
    nobody outside our infrastructure influences whether our own Slack lookup
    succeeds.
    """
    from src.domain.use_cases.slack_gateway_use_case import slack_user_profile

    profile = await slack_user_profile(external_user_id)
    slack_email = profile.get("email")
    if not slack_email:
        logger.warning(
            "identity link: email not verified (Slack would not tell us)",
            extra={
                "external_user_id": external_user_id,
                "slack_error": profile.get("error"),
                "hint": "grant users:read.email to enable this check",
            },
        )
        return False
    if not sgp_email:
        # Slack gave us an email but the SGP session didn't. Nothing to compare, so
        # the same rule applies: can't verify, don't block.
        logger.warning(
            "identity link: email not verified (no email on the SGP principal)",
            extra={"external_user_id": external_user_id},
        )
        return False
    return slack_email.strip().lower() != sgp_email.strip().lower()


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

    if not sgp_account_id:
        # The secrets service refuses a session credential with no account context
        # ("Account ID is required"), so a link without one would store a credential
        # that can never be used. Better to refuse now than to look connected and
        # quietly resolve nothing.
        logger.warning(
            "identity link refused: principal carried no account id",
            extra={"sgp_user_id": sgp_user_id},
        )
        return _page(
            "No account selected",
            "<h1>Couldn't finish connecting</h1>"
            "<p>Your session isn't scoped to an account.</p>"
            "<p class=muted>Open SGP, pick the account whose tools you want the "
            "agent to use, then click the link again.</p>",
            status=400,
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

    if await _email_mismatch(link_request.external_user_id, email):
        logger.warning(
            "identity link refused: Slack/SGP email mismatch",
            extra={
                "sgp_user_id": sgp_user_id,
                "external_user_id": link_request.external_user_id,
            },
        )
        return _page(
            "Accounts don't match",
            "<h1>Those accounts don't match</h1>"
            "<p>The Slack account this link was made for and the SGP account "
            "you're signed in as belong to different people.</p>"
            "<p class=muted>If someone sent you this link, don't use it — it "
            "would let their Slack messages run as you. Mention the agent in "
            "Slack yourself to get your own link.</p>",
            status=403,
        )

    secret = _session_credential(request)
    if not secret:
        # The middleware authenticated this caller somehow, but not by a session
        # cookie — an api-key or bearer caller, a cookie under a different name, or
        # cookie delegation switched off entirely. There is nothing here we can act
        # through later, so refuse rather than store an empty credential.
        logger.warning(
            "identity link refused: no session cookie on an authenticated request",
            extra={"sgp_user_id": sgp_user_id, "cookie": session_cookie_name()},
        )
        return _page(
            "Couldn't read your session",
            "<h1>Couldn't finish connecting</h1>"
            "<p>This needs to be opened in a browser signed in to SGP.</p>"
            "<p class=muted>If you're already signed in, open the link again in "
            "that same browser rather than a new window or a different app.</p>",
            status=400,
        )

    # The token's own expiry beats any TTL we could invent — the credential's real
    # lifetime belongs to the session. Unknown expiry falls back to a bounded
    # window rather than to "never".
    actual_expiry = session_jwt.expires_at(secret)
    if actual_expiry is None:
        actual_expiry = datetime.now(UTC) + timedelta(days=_FALLBACK_TTL_DAYS)
        logger.info(
            "identity link: session token declared no expiry; using fallback",
            extra={"sgp_user_id": sgp_user_id, "fallback_days": _FALLBACK_TTL_DAYS},
        )
    elif actual_expiry <= datetime.now(UTC):
        # Already expired: the middleware accepted it, but storing it would create a
        # link that cannot work. Say so instead of failing later and silently.
        return _page(
            "Session expired",
            "<h1>Your session has expired</h1>"
            "<p class=muted>Sign in to SGP again, then click the link once more.</p>",
            status=401,
        )

    try:
        await service.repository.upsert_link(
            provider=provider,
            external_team_id=link_request.external_team_id,
            external_user_id=link_request.external_user_id,
            sgp_user_id=sgp_user_id,
            sgp_account_id=sgp_account_id,
            linked_via=IdentityLinkMethod.EXPLICIT,
            credential=secret,
            credential_expires_at=actual_expiry,
        )
    except CredentialEncryptionError:
        # AGENTEX_CREDENTIAL_ENCRYPTION_KEY is missing or malformed, so the session
        # credential cannot be stored safely. Deliberately NOT stored in plaintext.
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
