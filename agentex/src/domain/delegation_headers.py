"""
Outbound runtime-delegation headers for ACP calls to agent pods (v1).

After auth, agentex may attach x-acting-user-* headers so agent pods can call
downstream APIs as the user. Values are minimal (never the full browser Cookie).

Session cookies: only configured names are forwarded on x-acting-user-cookie.
Default name is _identityJwt. Override with AGENTEX_DELEGATION_SESSION_COOKIE_NAMES
(comma-separated). Set to empty string to disable cookie delegation.
"""

import os
from typing import Any

HEADER_ACTING_USER_API_KEY = "x-acting-user-api-key"
HEADER_ACTING_USER_COOKIE = "x-acting-user-cookie"
HEADER_COOKIE = "cookie"
HEADER_SELECTED_ACCOUNT_ID = "x-selected-account-id"
HEADER_USER_API_KEY = "x-api-key"

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

    result: dict[str, str] = {}
    if api_key:
        result[HEADER_ACTING_USER_API_KEY] = api_key
    elif cookie_header:
        session_cookie = _minimal_session_cookie(
            cookie_header, session_cookie_names_to_forward()
        )
        if not session_cookie:
            return {}
        result[HEADER_ACTING_USER_COOKIE] = session_cookie
    else:
        return {}

    account_id = normalized.get(HEADER_SELECTED_ACCOUNT_ID)
    if account_id:
        result[HEADER_SELECTED_ACCOUNT_ID] = account_id

    return result
