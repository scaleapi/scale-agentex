"""
Outbound runtime-delegation headers for ACP calls to agent pods (v1).

Forwards the validated user API key on a dedicated header so agents can call
downstream APIs as the user. Agent identity for SGP will eventually be a claim
on a pod-minted delegation token (OBO), not a separate header from agentex.
"""

from typing import Any

HEADER_ACTING_USER_API_KEY = "x-acting-user-api-key"
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

    Requires a validated user principal from auth; reads x-api-key from the
    inbound request (already checked during auth). Skips delegation when the
    request is authenticated as the agent itself (agent_identity set).
    """
    if agent_identity or principal is None:
        return {}

    normalized = _normalize_headers(inbound_headers)
    api_key = normalized.get(HEADER_USER_API_KEY)
    if not api_key:
        return {}

    result = {
        HEADER_ACTING_USER_API_KEY: api_key,
    }

    account_id = normalized.get(HEADER_SELECTED_ACCOUNT_ID)
    if account_id:
        result[HEADER_SELECTED_ACCOUNT_ID] = account_id

    return result
