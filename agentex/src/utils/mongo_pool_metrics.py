"""MongoDB connection-pool (CMAP) metrics for the agentex Mongo client.

A pymongo pool listener that reports, via Datadog StatsD, what a command-level
span cannot: connection checkout wait/hold time, the live checked-out count, and
checkout failures (pool timeouts). No-op unless DD_AGENT_HOST is set.
"""

from __future__ import annotations

import os
import threading
import time

from datadog import statsd
from pymongo import monitoring

from src.utils.logging import make_logger

logger = make_logger(__name__)

# Only emit when the Datadog agent is configured (matches db_metrics.py).
_STATSD_ENABLED = bool(os.environ.get("DD_AGENT_HOST"))


class MongoPoolMetricsListener(monitoring.ConnectionPoolListener):
    """pymongo CMAP listener that emits connection-pool metrics to Datadog StatsD."""

    def __init__(
        self, service_name: str = "agentex", pool_name: str = "agentex-mongo"
    ) -> None:
        self._base_tags = [f"service:{service_name}", f"pool:{pool_name}"]
        # Callbacks fire from multiple threads; guard shared state.
        self._lock = threading.Lock()
        self._checked_out = 0
        # (address, connection_id) -> monotonic checkout timestamp
        self._checkout_started: dict[tuple, float] = {}

    def _emit_checked_out(self, current: int) -> None:
        if _STATSD_ENABLED:
            statsd.gauge(
                "mongo.client.connection.checked_out", current, tags=self._base_tags
            )

    def pool_created(self, event) -> None:
        pass

    def pool_ready(self, event) -> None:
        pass

    def pool_cleared(self, event) -> None:
        if _STATSD_ENABLED:
            statsd.increment("mongo.client.pool.cleared", tags=self._base_tags)

    def pool_closed(self, event) -> None:
        pass

    def connection_created(self, event) -> None:
        if _STATSD_ENABLED:
            statsd.increment("mongo.client.connection.created", tags=self._base_tags)

    def connection_ready(self, event) -> None:
        # event.duration = time to establish the connection (TCP + TLS + auth).
        # If this is high, opening connections to a DB near its ceiling is slow.
        if not _STATSD_ENABLED:
            return
        establish_ms = float(getattr(event, "duration", 0.0) or 0.0) * 1000.0
        statsd.histogram(
            "mongo.client.connection.establish_ms", establish_ms, tags=self._base_tags
        )

    def connection_closed(self, event) -> None:
        if _STATSD_ENABLED:
            reason = getattr(event, "reason", "") or ""
            statsd.increment(
                "mongo.client.connection.closed",
                tags=self._base_tags + [f"reason:{reason}"],
            )

    def connection_check_out_started(self, event) -> None:
        pass

    def connection_check_out_failed(self, event) -> None:
        # Pool-exhaustion timeouts (reason="timeout") surface here.
        if not _STATSD_ENABLED:
            return
        reason = getattr(event, "reason", "unknown")
        wait_ms = float(getattr(event, "duration", 0.0) or 0.0) * 1000.0
        statsd.increment(
            "mongo.client.connection.checkout_failed",
            tags=self._base_tags + [f"reason:{reason}"],
        )
        statsd.histogram(
            "mongo.client.connection.checkout_wait_ms",
            wait_ms,
            tags=self._base_tags + ["result:failed"],
        )

    def connection_checked_out(self, event) -> None:
        # event.duration is the time spent waiting to acquire a connection.
        wait_ms = float(getattr(event, "duration", 0.0) or 0.0) * 1000.0
        key = (event.address, event.connection_id)
        with self._lock:
            self._checked_out += 1
            self._checkout_started[key] = time.monotonic()
            current = self._checked_out
        if _STATSD_ENABLED:
            statsd.histogram(
                "mongo.client.connection.checkout_wait_ms",
                wait_ms,
                tags=self._base_tags + ["result:ok"],
            )
            self._emit_checked_out(current)

    def connection_checked_in(self, event) -> None:
        key = (event.address, event.connection_id)
        with self._lock:
            self._checked_out = max(0, self._checked_out - 1)
            started = self._checkout_started.pop(key, None)
            current = self._checked_out
        if not _STATSD_ENABLED:
            return
        if started is not None:
            hold_ms = (time.monotonic() - started) * 1000.0
            statsd.histogram(
                "mongo.client.connection.hold_ms", hold_ms, tags=self._base_tags
            )
        self._emit_checked_out(current)


_listener: MongoPoolMetricsListener | None = None


def get_mongo_pool_listener(
    service_name: str = "agentex", pool_name: str = "agentex-mongo"
) -> MongoPoolMetricsListener:
    """Return the process-wide singleton CMAP listener for the agentex Mongo client."""
    global _listener
    if _listener is None:
        _listener = MongoPoolMetricsListener(service_name, pool_name)
        logger.info("MongoDB pool metrics listener initialized")
    return _listener
