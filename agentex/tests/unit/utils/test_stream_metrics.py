"""Tests for the task-stream lifecycle metrics emitter.

Covers the two paths that matter operationally: the no-op path (neither OTel nor
StatsD configured, which is the default in tests and local dev) must never
raise, and the StatsD path must emit each metric with the expected name and
tags. The SSE stream path must never be disrupted by an instrumentation fault,
so emission errors must be swallowed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.utils import stream_metrics


@pytest.mark.unit
def test_record_functions_are_noop_when_unconfigured():
    # With no OTLP endpoint and no DD_AGENT_HOST, every call must be harmless.
    with (
        patch.object(stream_metrics, "_STATSD_ENABLED", False),
        patch.object(stream_metrics, "_opened_counter", None),
        patch.object(stream_metrics, "_closed_counter", None),
        patch.object(stream_metrics, "_duration_histogram", None),
        patch.object(stream_metrics, "_active_updown", None),
        patch.object(stream_metrics, "_stall_counter", None),
        patch.object(stream_metrics, "_instruments_initialized", True),
    ):
        stream_metrics.record_stream_opened()
        stream_metrics.record_stream_closed("completed", 1.5)
        stream_metrics.record_stream_stall()


@pytest.mark.unit
def test_record_functions_swallow_emission_errors():
    # A failing backend must never propagate to the caller (live SSE path).
    with (
        patch.object(stream_metrics, "_STATSD_ENABLED", True),
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_opened_counter", None),
        patch.object(stream_metrics, "_closed_counter", None),
        patch.object(stream_metrics, "_duration_histogram", None),
        patch.object(stream_metrics, "_active_updown", None),
        patch.object(stream_metrics, "_stall_counter", None),
        patch.object(stream_metrics, "statsd") as mock_statsd,
    ):
        mock_statsd.increment.side_effect = OSError("socket in a bad state")
        mock_statsd.histogram.side_effect = OSError("socket in a bad state")
        mock_statsd.gauge.side_effect = OSError("socket in a bad state")

        # None of these should raise despite the backend blowing up.
        stream_metrics.record_stream_opened()
        stream_metrics.record_stream_closed("error", 2.0)
        stream_metrics.record_stream_stall()


@pytest.mark.unit
def test_record_stream_opened_emits_statsd_when_enabled():
    with (
        patch.object(stream_metrics, "_STATSD_ENABLED", True),
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_opened_counter", None),
        patch.object(stream_metrics, "_active_updown", None),
        patch.object(stream_metrics, "_active_stream_count", 0),
        patch.object(stream_metrics, "statsd") as mock_statsd,
    ):
        stream_metrics.record_stream_opened()

    # Opening bumps the opened counter and reports the active concurrency level
    # as an absolute gauge (DogStatsD gauges are last-value-wins, not deltas).
    mock_statsd.increment.assert_called_once_with("agentex.task_stream.opened")
    mock_statsd.gauge.assert_called_once_with("agentex.task_stream.active", 1)


@pytest.mark.unit
def test_record_stream_closed_emits_statsd_when_enabled():
    with (
        patch.object(stream_metrics, "_STATSD_ENABLED", True),
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_closed_counter", None),
        patch.object(stream_metrics, "_duration_histogram", None),
        patch.object(stream_metrics, "_active_updown", None),
        patch.object(stream_metrics, "_active_stream_count", 1),
        patch.object(stream_metrics, "statsd") as mock_statsd,
    ):
        stream_metrics.record_stream_closed("client_disconnect", 3.25)

    mock_statsd.increment.assert_called_once_with(
        "agentex.task_stream.closed",
        tags=["outcome:client_disconnect"],
    )
    # Duration is reported to StatsD in milliseconds.
    mock_statsd.histogram.assert_called_once_with(
        "agentex.task_stream.duration", 3250.0
    )
    # Closing lowers the active gauge to the new absolute level (1 -> 0).
    mock_statsd.gauge.assert_called_once_with("agentex.task_stream.active", 0)


@pytest.mark.unit
def test_record_stream_stall_emits_statsd_when_enabled():
    with (
        patch.object(stream_metrics, "_STATSD_ENABLED", True),
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_stall_counter", None),
        patch.object(stream_metrics, "statsd") as mock_statsd,
    ):
        stream_metrics.record_stream_stall()

    mock_statsd.increment.assert_called_once_with("agentex.task_stream.stall")


@pytest.mark.unit
def test_closed_records_otel_instruments_with_outcome():
    # The OTel path records the outcome as a bounded attribute (not an id).
    opened, closed, duration, active, stall = (
        _FakeInstrument(),
        _FakeInstrument(),
        _FakeInstrument(),
        _FakeInstrument(),
        _FakeInstrument(),
    )
    with (
        patch.object(stream_metrics, "_STATSD_ENABLED", False),
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_opened_counter", opened),
        patch.object(stream_metrics, "_closed_counter", closed),
        patch.object(stream_metrics, "_duration_histogram", duration),
        patch.object(stream_metrics, "_active_updown", active),
        patch.object(stream_metrics, "_stall_counter", stall),
    ):
        stream_metrics.record_stream_opened()
        stream_metrics.record_stream_closed("error", 4.0)

    assert opened.calls == [(1, None)]
    assert closed.calls == [(1, {"outcome": "error"})]
    assert duration.calls == [(4.0, None)]
    # +1 on open, -1 on close nets to a balanced active gauge.
    assert active.calls == [(1, None), (-1, None)]


class _FakeInstrument:
    """Records (value, attributes) for add()/record() so tests can assert on them."""

    def __init__(self):
        self.calls: list[tuple[float, dict | None]] = []

    def add(self, value, attributes=None):
        self.calls.append((value, attributes))

    def record(self, value, attributes=None):
        self.calls.append((value, attributes))
