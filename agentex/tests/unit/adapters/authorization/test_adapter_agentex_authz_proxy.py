"""Unit tests for AgentexAuthorizationProxy.list_resources sentinel handling.

The proxy maps a provider's wildcard sentinel ({"unscoped": true}) onto the
existing unscoped path (None == no id filter), while ordinary {"items": [...]}
responses pass through as an inclusion filter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from src.adapters.authorization.adapter_agentex_authz_proxy import (
    AgentexAuthorizationProxy,
)
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)

PROXY_TARGET = (
    "src.adapters.authorization.adapter_agentex_authz_proxy."
    "HttpRequestHandler.post_with_error_handling"
)


def _proxy() -> AgentexAuthorizationProxy:
    return AgentexAuthorizationProxy(agentex_auth_url="http://auth.test")


@pytest.mark.unit
@pytest.mark.asyncio
class TestListResourcesSentinel:
    async def test_items_list_passes_through(self):
        with patch(PROXY_TARGET, new=AsyncMock(return_value={"items": ["a", "b"]})):
            result = await _proxy().list_resources(
                principal={"user_id": "u"},
                filter_resource=AgentexResourceType.task,
                filter_operation=AuthorizedOperationType.read,
            )
        assert result == ["a", "b"]

    async def test_unscoped_true_returns_none(self):
        with patch(PROXY_TARGET, new=AsyncMock(return_value={"unscoped": True})):
            result = await _proxy().list_resources(
                principal={"user_id": "u"},
                filter_resource=AgentexResourceType.task,
            )
        assert result is None

    async def test_unscoped_wins_over_items(self):
        with patch(
            PROXY_TARGET,
            new=AsyncMock(return_value={"unscoped": True, "items": ["x"]}),
        ):
            result = await _proxy().list_resources(
                principal={"user_id": "u"},
                filter_resource=AgentexResourceType.task,
            )
        assert result is None

    async def test_empty_items_is_not_a_sentinel(self):
        with patch(PROXY_TARGET, new=AsyncMock(return_value={"items": []})):
            result = await _proxy().list_resources(
                principal={"user_id": "u"},
                filter_resource=AgentexResourceType.task,
            )
        assert result == []

    async def test_truthy_non_boolean_unscoped_is_not_a_sentinel(self):
        # 1 is truthy but `1 is True` is False, so the strict identity check must
        # not treat it as the sentinel; only the JSON boolean `true` qualifies.
        with patch(
            PROXY_TARGET,
            new=AsyncMock(return_value={"unscoped": 1, "items": []}),
        ):
            result = await _proxy().list_resources(
                principal={"user_id": "u"},
                filter_resource=AgentexResourceType.task,
            )
        assert result == []

    async def test_missing_unscoped_and_items_fails_closed(self):
        # A malformed response with neither field must raise rather than silently
        # return [] or None — the guard against a provider accidentally failing open.
        with patch(
            PROXY_TARGET,
            new=AsyncMock(return_value={"unexpected_key": "val"}),
        ):
            with pytest.raises(KeyError):
                await _proxy().list_resources(
                    principal={"user_id": "u"},
                    filter_resource=AgentexResourceType.task,
                )
