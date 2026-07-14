"""
Outbound runtime-delegation headers for ACP calls to agent pods (v1).

After auth, agentex may attach x-acting-user-* headers so agent pods can call
downstream APIs as the user. Values are minimal (never the full browser Cookie).

Three credential forms are forwarded, in precedence order:
  1. x-api-key            -> x-acting-user-api-key
  2. session cookie       -> x-acting-user-cookie
  3. Authorization bearer -> x-acting-user-authorization

Session cookies: only configured names are forwarded on x-acting-user-cookie.
Default name is _identityJwt. Override with AGENTEX_DELEGATION_SESSION_COOKIE_NAMES
(comma-separated). Set to empty string to disable cookie delegation.

The bearer branch is the lowest-precedence fallback: it only fires when neither an
api key nor a session cookie is present. Callers authenticated by an OIDC/OneAuth
access token (bearer, no api key or session cookie) land here, so the agent pod can
present the same bearer to downstream APIs that accept it.
"""

import os
from typing import Any

HEADER_ACTING_USER_API_KEY = "x-acting-user-api-key"
HEADER_ACTING_USER_COOKIE = "x-acting-user-cookie"
HEADER_ACTING_USER_AUTHORIZATION = "x-acting-user-authorization"
HEADER_AUTHORIZATION = "authorization"
HEADER_COOKIE = "cookie"
HEADER_SELECTED_ACCOUNT_ID = "x-selected-account-id"
HEADER_USER_API_KEY = "x-api-key"

_BEARER_PREFIX = "bearer "

ENV_SESSION_COOKIE_NAMES = "AGENTEX_DELEGATION_SESSION_COOKIE_NAMES"
DEFAULT_SESSION_COOKIE_NAMES = ("_identityJwt",)


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {k.lower(): v for k, v in headers.items()}


def session_cookie_names_to_forward() -> tuple[str, ...]:
    """Cookie names to include in x-acting-user-cookie. Unset env uses the default."""
    raw = os.environ.get(ENV_SESSION_COOKIE_NAMES)
    if raw is None:
        return DEFAULT_SESSION_COOKIE_NAMES
    raw = raw.strip()
    if not raw:
        return ()
    return tuple(name.strip() for name in raw.split(",") if name.strip())


def _minimal_session_cookie(cookie_header: str, names: tuple[str, ...]) -> str | None:
    """Extract only the allowlisted session cookies from an inbound Cookie header.

    We parse the header by hand rather than via ``http.cookies.SimpleCookie``.
    Real browsers send a long, messy Cookie header full of third-party/analytics
    morsels that ``SimpleCookie`` cannot parse — e.g. ``__utmzz`` values containing
    spaces and parentheses (``(not set)``), ``fs_uid`` containing ``#``, or base64
    values ending in ``==``. When ``SimpleCookie.load()`` hits one of those it stops
    and silently drops the remaining morsels, so a perfectly valid ``_identityJwt``
    sitting later in the header is lost and cookie delegation breaks entirely (the
    agent pod then gets no acting credential). Since we only ever forward exact
    ``name=value`` pairs for a small allowlist, splitting on ``;`` is both more robust
    and sufficient — and it never trusts/decodes the non-allowlisted cookies.
    """
    if not names:
        return None

    jar: dict[str, str] = {}
    for part in cookie_header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep:
            # First occurrence wins, matching prior SimpleCookie behavior.
            jar.setdefault(name.strip(), value.strip())

    pairs = [f"{name}={jar[name]}" for name in names if name in jar]
    return "; ".join(pairs) if pairs else None


def build_delegation_headers(
    principal: Any,
    inbound_headers: dict[str, str] | None,
    *,
    agent_identity: str | None = None,
) -> dict[str, str]:
    """Build outbound acting headers for an authenticated user invocation."""
    if agent_identity or principal is None:
        return {}

    normalized = _normalize_headers(inbound_headers)
    api_key = normalized.get(HEADER_USER_API_KEY)
    cookie_header = normalized.get(HEADER_COOKIE)
    authorization = normalized.get(HEADER_AUTHORIZATION)

    # Resolve the session cookie up front: a Cookie header carrying only
    # non-allowlisted morsels (analytics, CSRF) yields nothing, and must not
    # pre-empt a bearer that rides alongside it (browser OIDC callers send both).
    session_cookie = (
        _minimal_session_cookie(cookie_header, session_cookie_names_to_forward())
        if cookie_header
        else None
    )

    result: dict[str, str] = {}
    if api_key:
        result[HEADER_ACTING_USER_API_KEY] = api_key
    elif session_cookie:
        result[HEADER_ACTING_USER_COOKIE] = session_cookie
    elif authorization and authorization.lower().startswith(_BEARER_PREFIX):
        result[HEADER_ACTING_USER_AUTHORIZATION] = authorization
    else:
        return {}

    account_id = normalized.get(HEADER_SELECTED_ACCOUNT_ID)
    if account_id:
        result[HEADER_SELECTED_ACCOUNT_ID] = account_id

    return result
