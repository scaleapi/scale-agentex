"""
Metrics instrumentation for the task-event SSE stream lifecycle.

Mirrors the dual-emit pattern in ``src/utils/cache_metrics.py``:

- When an OTLP endpoint is configured (``OTEL_EXPORTER_OTLP_ENDPOINT``), the
  instruments are recorded through the OpenTelemetry SDK.
- When the Datadog Agent is reachable (``DD_AGENT_HOST``), the same events are
  emitted as StatsD metrics.
- When neither is configured, every function here is a cheap no-op.

**Why this exists (see AGX1-616/AGX1-618):** HTTP request-level RED for
``GET /tasks/{task_id}/stream`` is already covered by auto-instrumentation — the
route records into ``http_server_request_duration_seconds`` at connection close.
But a single SSE request produces exactly one duration sample, which says nothing
about what happened *during* the stream's life: how many were concurrently open,
whether a stream ended normally vs. by client disconnect vs. by error, or whether
a stream went quiet (no events pushed) for a stretch. Those are the stream-
lifecycle signals request-level instrumentation cannot express, and they are what
this module adds.

Instrument names are deliberately dotted (``agentex.task_stream.*``); the OTLP →
Prometheus translation flattens dots to underscores, appends ``_total`` to
monotonic counters, and appends the unit (``s`` → ``_seconds``) to the histogram,
so the series land in Mimir as ``agentex_task_stream_opened_total``,
``agentex_task_stream_closed_total``, ``agentex_task_stream_duration_seconds``,
``agentex_task_stream_active`` and ``agentex_task_stream_stall_total``. These
hand-instrumented series carry only bounded attributes (``outcome``) and no
``http_route`` label — group by ``outcome``, not ``http_route``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from datadog import statsd

from src.utils.logging import make_logger
from src.utils.otel_metrics import get_meter

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram, UpDownCounter

logger = make_logger(__name__)

# StatsD is only emitted if the Datadog Agent host is configured.
_STATSD_ENABLED = bool(os.environ.get("DD_AGENT_HOST"))

# How a stream ended. "completed" = the generator returned normally;
# "client_disconnect" = the client went away (asyncio.CancelledError);
# "error" = the stream loop raised a fatal, non-recoverable exception. HTTP
# status 200 at connection close cannot tell these three apart, which is why the
# distinction lives here as a bounded label rather than on the request metric.
StreamOutcome = Literal["completed", "client_disconnect", "error"]

# Lazily-created OTel instruments (created once, on first use).
_opened_counter: Counter | None = None
_closed_counter: Counter | None = None
_duration_histogram: Histogram | None = None
_active_updown: UpDownCounter | None = None
_stall_counter: Counter | None = None
_instruments_initialized = False


def _ensure_instruments() -> None:
    """Create the OTel instruments on first use. No-op if OTel is not configured."""
    global _opened_counter, _closed_counter, _duration_histogram
    global _active_updown, _stall_counter, _instruments_initialized

    if _instruments_initialized:
        return
    _instruments_initialized = True

    meter = get_meter("agentex.task_stream")
    if meter is None:
        # OTel not configured; OTel path stays disabled. StatsD may still emit.
        return

    _opened_counter = meter.create_counter(
        name="agentex.task_stream.opened",
        description="Task-event SSE streams opened",
        unit="{stream}",
    )
    _closed_counter = meter.create_counter(
        name="agentex.task_stream.closed",
        description="Task-event SSE streams closed, tagged by outcome",
        unit="{stream}",
    )
    _duration_histogram = meter.create_histogram(
        name="agentex.task_stream.duration",
        description="Task-event SSE stream lifetime",
        unit="s",
    )
    _active_updown = meter.create_up_down_counter(
        name="agentex.task_stream.active",
        description="Currently open task-event SSE streams",
        unit="{stream}",
    )
    _stall_counter = meter.create_counter(
        name="agentex.task_stream.stall",
        description="Task-event SSE streams that went idle (no event pushed) past the stall threshold",
        unit="{stream}",
    )


def record_stream_opened() -> None:
    """
    Record a task-event stream opening: bumps the opened counter and the active gauge.

    Pair every call with exactly one ``record_stream_closed`` so the active gauge
    stays balanced. Never raises: see ``record_stream_closed``.
    """
    try:
        _ensure_instruments()

        if _opened_counter is not None:
            _opened_counter.add(1)
        if _active_updown is not None:
            _active_updown.add(1)

        if _STATSD_ENABLED:
            statsd.increment("agentex.task_stream.opened")
            # No StatsD "active" gauge: concurrency is OTel-only. DogStatsD
            # gauges are last-write-wins per flush, so N workers each emitting a
            # process-local count would make the gauge flap between workers
            # rather than sum to the true concurrency. The OTel UpDownCounter
            # sums correctly across per-instance series at query time.
    except Exception:
        logger.debug("Failed to emit agentex.task_stream.opened metric", exc_info=True)


def record_stream_closed(outcome: StreamOutcome, duration_seconds: float) -> None:
    """
    Record a task-event stream closing: bumps the closed counter (tagged by
    outcome), records the stream lifetime, and lowers the active gauge.

    Args:
        outcome: One of "completed", "client_disconnect", "error".
        duration_seconds: How long the stream was open.

    Never raises: emission failures (e.g. a StatsD UDP socket error or an OTel
    SDK fault) are swallowed so instrumentation can never disrupt the SSE path.
    """
    try:
        _ensure_instruments()

        if _closed_counter is not None:
            _closed_counter.add(1, {"outcome": outcome})
        if _duration_histogram is not None:
            _duration_histogram.record(duration_seconds)
        if _active_updown is not None:
            _active_updown.add(-1)

        if _STATSD_ENABLED:
            statsd.increment("agentex.task_stream.closed", tags=[f"outcome:{outcome}"])
            # Datadog histograms conventionally take milliseconds for durations.
            statsd.histogram("agentex.task_stream.duration", duration_seconds * 1000)
            # No StatsD "active" gauge — concurrency is OTel-only; a per-worker
            # DogStatsD gauge would flap rather than sum (see record_stream_opened).
    except Exception:
        logger.debug("Failed to emit agentex.task_stream.closed metric", exc_info=True)


def record_stream_stall() -> None:
    """
    Record that an open stream went idle — no event pushed to the client for
    longer than the configured stall threshold. Emit once per stall episode
    (the caller de-dupes) so the counter measures stall onsets, not idle cycles.

    Never raises: see ``record_stream_closed``.
    """
    try:
        _ensure_instruments()

        if _stall_counter is not None:
            _stall_counter.add(1)

        if _STATSD_ENABLED:
            statsd.increment("agentex.task_stream.stall")
    except Exception:
        logger.debug("Failed to emit agentex.task_stream.stall metric", exc_info=True)
