"""
Metrics instrumentation for the task-event SSE stream lifecycle.

Emission is OpenTelemetry-only:

- When an OTLP endpoint is configured (``OTEL_EXPORTER_OTLP_ENDPOINT``), the
  instruments are recorded through the OpenTelemetry SDK.
- When it is not configured, every function here is a cheap no-op.

Unlike the older ``cache_metrics.py`` dual-emit path, there is no direct
StatsD/DogStatsD emission here. These are new metrics, and the target state
routes OTel to Datadog through the collector rather than emitting to the Datadog
Agent directly — so a second, DogStatsD-native copy of every point would just be
redundant.

**Why this exists:** HTTP request-level RED for
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

from typing import TYPE_CHECKING, Literal

from src.utils.logging import make_logger
from src.utils.otel_metrics import get_meter

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram, UpDownCounter

logger = make_logger(__name__)

# How a stream ended. "completed" = the generator returned normally;
# "client_disconnect" = the client went away (asyncio.CancelledError);
# "error" = the stream loop raised a fatal, non-recoverable exception. HTTP
# status 200 at connection close cannot tell these three apart, which is why the
# distinction lives here as a bounded label rather than on the request metric.
StreamOutcome = Literal["completed", "client_disconnect", "error"]

# Bucket boundaries (seconds) for the stream-lifetime histogram, spanning 1s to
# 4h. SSE streams are long-lived — seconds to hours — so without this advisory
# the SDK falls back to its millisecond-scale default boundaries [0, 5, 10, 25,
# ... 10000] and every stream shorter than 10s piles into one bucket while
# anything past ~2.8h overflows to +Inf. See rpc_metrics.py / db_metrics.py for
# the same pattern.
_DURATION_BUCKET_BOUNDARIES_S = (
    1.0,
    5.0,
    15.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    1800.0,
    3600.0,
    7200.0,
    14400.0,
)

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
        # OTel not configured; every record_* call stays a no-op.
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
        explicit_bucket_boundaries_advisory=_DURATION_BUCKET_BOUNDARIES_S,
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
    except Exception:
        logger.debug("Failed to emit agentex.task_stream.opened metric", exc_info=True)


def record_stream_closed(outcome: StreamOutcome, duration_seconds: float) -> None:
    """
    Record a task-event stream closing: bumps the closed counter (tagged by
    outcome), records the stream lifetime (also tagged by outcome), and lowers
    the active gauge.

    Args:
        outcome: One of "completed", "client_disconnect", "error".
        duration_seconds: How long the stream was open.

    Never raises: emission failures (e.g. an OTel SDK fault) are swallowed so
    instrumentation can never disrupt the SSE path.
    """
    try:
        _ensure_instruments()

        if _closed_counter is not None:
            _closed_counter.add(1, {"outcome": outcome})
        if _duration_histogram is not None:
            _duration_histogram.record(duration_seconds, {"outcome": outcome})
        if _active_updown is not None:
            _active_updown.add(-1)
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
    except Exception:
        logger.debug("Failed to emit agentex.task_stream.stall metric", exc_info=True)
