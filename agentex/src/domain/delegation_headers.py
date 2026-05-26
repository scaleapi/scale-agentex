"""
Outbound runtime-delegation headers for ACP calls to agent pods (v1).

Forwards the validated user credential on dedicated headers so agents can call
downstream APIs as the user: API key via x-acting-user-api-key, session JWT via
x-acting-user-cookie (full Cookie header value, typically _identityJwt=...).
Agent identity for SGP will eventually be a claim on a pod-minted delegation
token (OBO), not separate headers from agentex.
"""

from typing import Any

HEADER_ACTING_USER_API_KEY = "x-acting-user-api-key"
HEADER_ACTING_USER_COOKIE = "x-acting-user-cookie"
HEADER_COOKIE = "cookie"
HEADER_SELECTED_ACCOUNT_ID = "x-selected-account-id"
HEADER_USER_API_KEY = "x-api-key"


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {k.lower(): v for k, v in headers.items()}


def build_delegation_headers(
    principal: Any,
    inbound_headers: dict[str, str] | None,
    *,
    agent_identity: str | None = None,
) -> dict[str, str]:
    """
    Outbound ACP headers so the agent can act on behalf of the authenticated user.

    Requires a validated user principal from auth. Copies x-api-key or Cookie
    from the inbound request (already checked during auth). Prefers API key when
    both are present. Skips delegation when the request is authenticated as the
    agent itself (agent_identity set).
    """
    if agent_identity or principal is None:
        return {}

    normalized = _normalize_headers(inbound_headers)
    api_key = normalized.get(HEADER_USER_API_KEY)
    cookie = normalized.get(HEADER_COOKIE)

    result: dict[str, str] = {}
    if api_key:
        result[HEADER_ACTING_USER_API_KEY] = api_key
    elif cookie:
        result[HEADER_ACTING_USER_COOKIE] = cookie
    else:
        return {}

    account_id = normalized.get(HEADER_SELECTED_ACCOUNT_ID)
    if account_id:
        result[HEADER_SELECTED_ACCOUNT_ID] = account_id

    return result
