"""Outbound runtime-delegation headers for ACP calls to agent pods."""

from typing import Any

HEADER_ACTING_AS_AGENT = "x-acting-as-agent"
HEADER_ACTING_USER_API_KEY = "x-acting-user-api-key"
HEADER_SELECTED_ACCOUNT_ID = "x-selected-account-id"
HEADER_USER_API_KEY = "x-api-key"


def _normalize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {k.lower(): v for k, v in headers.items()}


def build_delegation_headers(
    principal: Any,
    agent_id: str,
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
        HEADER_ACTING_AS_AGENT: agent_id,
    }

    account_id = normalized.get(HEADER_SELECTED_ACCOUNT_ID)
    if account_id:
        result[HEADER_SELECTED_ACCOUNT_ID] = account_id

    return result
