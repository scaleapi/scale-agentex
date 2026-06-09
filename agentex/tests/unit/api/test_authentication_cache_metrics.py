"""Tests for cache hit/miss/eviction instrumentation in ``authentication_cache``.

Asserts that ``AsyncTTLCache`` records the correct metric for each of the three
read outcomes (hit / miss_expired / miss_absent) and emits an eviction metric on
capacity-driven LRU eviction. The emission backend (OTel / StatsD) is covered
separately; here we patch the recorder functions at their import site in
``authentication_cache`` and assert the calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.api.authentication_cache import AsyncTTLCache, AuthenticationCache
from src.api.schemas.principal_context import AgentexAuthPrincipalContext


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncTTLCacheMetrics:
    async def test_hit_records_hit(self):
        cache = AsyncTTLCache(name="agent_api_key", ttl_seconds=300)
        await cache.set("k", "v")

        with patch("src.api.authentication_cache.record_cache_access") as record_access:
            result = await cache.get("k")

        assert result == "v"
        record_access.assert_called_once_with("agent_api_key", "hit")

    async def test_absent_key_records_miss_absent(self):
        cache = AsyncTTLCache(name="auth_gateway", ttl_seconds=300)

        with patch("src.api.authentication_cache.record_cache_access") as record_access:
            result = await cache.get("never-set")

        assert result is None
        record_access.assert_called_once_with("auth_gateway", "miss_absent")

    async def test_expired_entry_records_miss_expired(self):
        cache = AsyncTTLCache(name="auth_gateway", ttl_seconds=60)
        await cache.set("k", "v")
        # Force expiry deterministically by backdating the stored timestamp,
        # avoiding any reliance on wall-clock timing in the test.
        value, _ = cache.cache["k"]
        cache.cache["k"] = (value, 0.0)

        with patch("src.api.authentication_cache.record_cache_access") as record_access:
            result = await cache.get("k")

        assert result is None
        record_access.assert_called_once_with("auth_gateway", "miss_expired")
        # The expired entry should also have been purged from the cache.
        assert "k" not in cache.cache

    async def test_capacity_eviction_records_eviction(self):
        cache = AsyncTTLCache(name="authorization_check", max_size=1, ttl_seconds=300)
        await cache.set("first", "v1")

        with patch(
            "src.api.authentication_cache.record_cache_eviction"
        ) as record_eviction:
            # Inserting a second distinct key evicts the oldest (LRU).
            await cache.set("second", "v2")

        record_eviction.assert_called_once_with("authorization_check")
        assert "first" not in cache.cache
        assert "second" in cache.cache

    async def test_overwriting_existing_key_does_not_evict(self):
        cache = AsyncTTLCache(name="authorization_check", max_size=1, ttl_seconds=300)
        await cache.set("k", "v1")

        with patch(
            "src.api.authentication_cache.record_cache_eviction"
        ) as record_eviction:
            # Re-setting an existing key is an update, not a capacity eviction.
            await cache.set("k", "v2")

        record_eviction.assert_not_called()
        assert await cache.get("k") == "v2"


@pytest.mark.unit
def test_authentication_cache_assigns_distinct_names():
    """Each sub-cache carries the name used as the ``cache`` metric tag."""
    cache = AuthenticationCache()

    assert cache.agent_identity_cache.name == "agent_identity"
    assert cache.agent_api_key_cache.name == "agent_api_key"
    assert cache.auth_gateway_cache.name == "auth_gateway"
    assert cache.authorization_check_cache.name == "authorization_check"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auth_gateway_response_with_api_key_principal_is_sanitized_before_cache():
    cache = AuthenticationCache()
    headers = {"x-api-key": "secret-key", "x-selected-account-id": "acct-1"}
    principal = {"user_id": "user-1", "account_id": "acct-1", "api_key": "secret-key"}

    await cache.set_auth_gateway_response(headers, principal)

    cached_principal = await cache.get_auth_gateway_response(headers)

    assert isinstance(cached_principal, AgentexAuthPrincipalContext)
    assert cached_principal.model_dump(exclude_none=True) == {
        "user_id": "user-1",
        "account_id": "acct-1",
    }
