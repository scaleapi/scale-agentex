"""Tests for the auth-cache metrics emitter.

Covers the two paths that matter operationally: the no-op path (neither OTel nor
StatsD configured, which is the default in tests and local dev) must never
raise, and the StatsD path must emit a counter with the expected name and tags.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.utils import cache_metrics


@pytest.mark.unit
def test_record_functions_are_noop_when_unconfigured():
    # With no OTLP endpoint and no DD_AGENT_HOST, both calls must be harmless.
    with (
        patch.object(cache_metrics, "_STATSD_ENABLED", False),
        patch.object(cache_metrics, "_access_counter", None),
        patch.object(cache_metrics, "_eviction_counter", None),
        patch.object(cache_metrics, "_instruments_initialized", True),
    ):
        cache_metrics.record_cache_access("auth_gateway", "hit")
        cache_metrics.record_cache_eviction("auth_gateway")


@pytest.mark.unit
def test_record_functions_swallow_emission_errors():
    # A failing backend must never propagate to the caller (critical auth path).
    with (
        patch.object(cache_metrics, "_STATSD_ENABLED", True),
        patch.object(cache_metrics, "_instruments_initialized", True),
        patch.object(cache_metrics, "_access_counter", None),
        patch.object(cache_metrics, "_eviction_counter", None),
        patch.object(cache_metrics, "statsd") as mock_statsd,
    ):
        mock_statsd.increment.side_effect = OSError("socket in a bad state")

        # Neither call should raise despite the backend blowing up.
        cache_metrics.record_cache_access("auth_gateway", "hit")
        cache_metrics.record_cache_eviction("auth_gateway")


@pytest.mark.unit
def test_record_cache_access_emits_statsd_when_enabled():
    with (
        patch.object(cache_metrics, "_STATSD_ENABLED", True),
        patch.object(cache_metrics, "_instruments_initialized", True),
        patch.object(cache_metrics, "_access_counter", None),
        patch.object(cache_metrics, "statsd") as mock_statsd,
    ):
        cache_metrics.record_cache_access("auth_gateway", "miss_absent")

    mock_statsd.increment.assert_called_once_with(
        "auth_cache.access",
        tags=["cache:auth_gateway", "result:miss_absent"],
    )


@pytest.mark.unit
def test_record_cache_eviction_emits_statsd_when_enabled():
    with (
        patch.object(cache_metrics, "_STATSD_ENABLED", True),
        patch.object(cache_metrics, "_instruments_initialized", True),
        patch.object(cache_metrics, "_eviction_counter", None),
        patch.object(cache_metrics, "statsd") as mock_statsd,
    ):
        cache_metrics.record_cache_eviction("agent_api_key")

    mock_statsd.increment.assert_called_once_with(
        "auth_cache.eviction",
        tags=["cache:agent_api_key"],
    )
