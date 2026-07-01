"""
Metrics instrumentation for Temporal-backed agent run schedule operations.

Mirrors the dual-emit pattern in ``src/utils/cache_metrics.py``:

- When an OTLP endpoint is configured (``OTEL_EXPORTER_OTLP_ENDPOINT``), counters
  are recorded through the OpenTelemetry SDK.
- When the Datadog Agent is reachable (``DD_AGENT_HOST``), the same events are
  emitted as StatsD counters.
- When neither is configured, every function here is a cheap no-op.

The goal is to make the schedule's Temporal lifecycle observable: how often each
create/update/delete succeeds, hits a missing schedule, or errors out. These are
the signals needed to tell whether schedule operations are healthy or whether the
Temporal clock is drifting out of sync with the Postgres source of truth.
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

# The Temporal schedule lifecycle operation being recorded.
ScheduleOperation = Literal["create", "update", "delete"]

# Outcome of a single operation. "success" = the Temporal call completed;
# "not_found" = the schedule was already absent (TemporalScheduleNotFoundError);
# "error" = any other failure.
ScheduleResult = Literal["success", "not_found", "error"]

# Lazily-created OTel instrument (created once, on first use).
_op_counter: Counter | None = None
_instruments_initialized = False


def _ensure_instruments() -> None:
    """Create the OTel counter on first use. No-op if OTel is not configured."""
    global _op_counter, _instruments_initialized

    if _instruments_initialized:
        return
    _instruments_initialized = True

    meter = get_meter("agentex.agent_run_schedule")
    if meter is None:
        # OTel not configured; OTel path stays disabled. StatsD may still emit.
        return

    _op_counter = meter.create_counter(
        name="agent_run_schedule.temporal_op",
        description="Temporal schedule lifecycle operations, tagged by operation and result",
        unit="{operation}",
    )


def record_schedule_temporal_op(
    operation: ScheduleOperation, result: ScheduleResult
) -> None:
    """
    Record a single Temporal schedule lifecycle operation.

    Args:
        operation: One of "create", "update", "delete".
        result: One of "success", "not_found", "error".

    Never raises: emission failures (e.g. a StatsD UDP socket error or an OTel
    SDK fault) are swallowed so instrumentation can never disrupt a caller on
    the schedule path.
    """
    try:
        _ensure_instruments()

        if _op_counter is not None:
            _op_counter.add(1, {"operation": operation, "result": result})

        if _STATSD_ENABLED:
            statsd.increment(
                "agent_run_schedule.temporal_op",
                tags=[f"operation:{operation}", f"result:{result}"],
            )
    except Exception:
        logger.debug(
            "Failed to emit agent_run_schedule.temporal_op metric", exc_info=True
        )
