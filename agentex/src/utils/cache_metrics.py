"""
Metrics instrumentation for the in-process authentication/authorization caches.

Mirrors the dual-emit pattern in ``src/utils/db_metrics.py``:

- When an OTLP endpoint is configured (``OTEL_EXPORTER_OTLP_ENDPOINT``), counters
  are recorded through the OpenTelemetry SDK.
- When the Datadog Agent is reachable (``DD_AGENT_HOST``), the same events are
  emitted as StatsD counters.
- When neither is configured, every function here is a cheap no-op.

The goal is to make cache effectiveness observable: hit rate per cache, the
reason for misses (expired vs never-seen), and capacity-driven evictions. These
are exactly the signals needed to tell whether a low hit rate is a TTL problem,
a key-cardinality problem, or a capacity problem.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from datadog import statsd

from src.utils.logging import make_logger
from src.utils.otel_metrics import get_meter

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter

logger = make_logger(__name__)

# StatsD is only emitted if the Datadog Agent host is configured.
_STATSD_ENABLED = bool(os.environ.get("DD_AGENT_HOST"))

# Outcome of a single cache read. "hit" = present and fresh; "miss_expired" =
# present but past its TTL (TTL too short / churn); "miss_absent" = never cached
# or evicted (cold cache, key never repeats, or capacity eviction).
CacheResult = Literal["hit", "miss_expired", "miss_absent"]

# Lazily-created OTel instruments (created once, on first use).
_access_counter: Counter | None = None
_eviction_counter: Counter | None = None
_instruments_initialized = False


def _ensure_instruments() -> None:
    """Create OTel counters on first use. No-op if OTel is not configured."""
    global _access_counter, _eviction_counter, _instruments_initialized

    if _instruments_initialized:
        return
    _instruments_initialized = True

    meter = get_meter("agentex.auth_cache")
    if meter is None:
        # OTel not configured; OTel path stays disabled. StatsD may still emit.
        return

    _access_counter = meter.create_counter(
        name="auth_cache.access",
        description="Authentication/authorization cache reads, tagged by cache and result",
        unit="{access}",
    )
    _eviction_counter = meter.create_counter(
        name="auth_cache.eviction",
        description="LRU evictions from authentication/authorization caches",
        unit="{eviction}",
    )


def record_cache_access(cache_name: str, result: CacheResult) -> None:
    """
    Record a single cache read.

    Args:
        cache_name: Logical cache name (e.g. "auth_gateway", "agent_api_key").
        result: One of "hit", "miss_expired", "miss_absent".
    """
    _ensure_instruments()

    if _access_counter is not None:
        _access_counter.add(1, {"cache": cache_name, "result": result})

    if _STATSD_ENABLED:
        statsd.increment(
            "auth_cache.access",
            tags=[f"cache:{cache_name}", f"result:{result}"],
        )


def record_cache_eviction(cache_name: str) -> None:
    """Record a single capacity-driven (LRU) eviction."""
    _ensure_instruments()

    if _eviction_counter is not None:
        _eviction_counter.add(1, {"cache": cache_name})

    if _STATSD_ENABLED:
        statsd.increment("auth_cache.eviction", tags=[f"cache:{cache_name}"])
