"""Event-loop lag instrumentation.

Measures how late a fixed-interval wake-up actually fires — i.e. the asyncio
event loop's scheduling delay. Low lag means the loop resumes coroutines
promptly; high lag means the loop is stalled (a blocking call or
oversubscription), so awaiting coroutines — and any pooled connections they
hold — are released late. Emitted as a histogram so peak stalls are visible.

No-op unless DD_AGENT_HOST is set.

Metric: agentex.event_loop.lag_ms  (histogram)  tags: service
"""

from __future__ import annotations

import asyncio
import os

from datadog import statsd

from src.utils.logging import make_logger

logger = make_logger(__name__)

_STATSD_ENABLED = bool(os.environ.get("DD_AGENT_HOST"))
# Wake every 100ms; how far past 100ms the wake-up actually fires is the lag.
_SAMPLE_INTERVAL_S = 0.1

_monitor_task: asyncio.Task | None = None


async def _run(service_name: str) -> None:
    loop = asyncio.get_running_loop()
    tags = [f"service:{service_name}"]
    while True:
        start = loop.time()
        try:
            await asyncio.sleep(_SAMPLE_INTERVAL_S)
        except asyncio.CancelledError:
            break
        lag_ms = max(0.0, (loop.time() - start - _SAMPLE_INTERVAL_S) * 1000.0)
        if _STATSD_ENABLED:
            statsd.histogram("agentex.event_loop.lag_ms", lag_ms, tags=tags)


def start_event_loop_lag_monitor(service_name: str = "agentex") -> None:
    """Start the background event-loop lag monitor (idempotent)."""
    global _monitor_task
    if _monitor_task is not None and not _monitor_task.done():
        return
    _monitor_task = asyncio.create_task(_run(service_name))
    logger.info("Event-loop lag monitor started")


async def stop_event_loop_lag_monitor() -> None:
    """Stop the background event-loop lag monitor."""
    global _monitor_task
    if _monitor_task is None:
        return
    _monitor_task.cancel()
    try:
        await _monitor_task
    except asyncio.CancelledError:
        pass
    _monitor_task = None
    logger.info("Event-loop lag monitor stopped")
