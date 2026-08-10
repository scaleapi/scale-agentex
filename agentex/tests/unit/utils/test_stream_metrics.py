"""Tests for the task-stream lifecycle metrics emitter.

Emission is OpenTelemetry-only. Two paths matter operationally: the no-op path
(OTel not configured, which is the default in tests and local dev) must never
raise, and the OTel path must record each instrument with the expected value and
bounded attributes. The SSE stream path must never be disrupted by an
instrumentation fault, so emission errors must be swallowed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.utils import stream_metrics


@pytest.mark.unit
def test_record_functions_are_noop_when_unconfigured():
    # With no OTLP endpoint the instruments stay None, so every call is harmless.
    with (
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
    # A failing instrument must never propagate to the caller (live SSE path).
    exploding = _ExplodingInstrument()
    with (
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_opened_counter", exploding),
        patch.object(stream_metrics, "_closed_counter", exploding),
        patch.object(stream_metrics, "_duration_histogram", exploding),
        patch.object(stream_metrics, "_active_updown", exploding),
        patch.object(stream_metrics, "_stall_counter", exploding),
    ):
        # None of these should raise despite the instrument blowing up.
        stream_metrics.record_stream_opened()
        stream_metrics.record_stream_closed("error", 2.0)
        stream_metrics.record_stream_stall()


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
    assert duration.calls == [(4.0, {"outcome": "error"})]
    # +1 on open, -1 on close nets to a balanced active gauge.
    assert active.calls == [(1, None), (-1, None)]


@pytest.mark.unit
def test_stall_records_otel_counter():
    stall = _FakeInstrument()
    with (
        patch.object(stream_metrics, "_instruments_initialized", True),
        patch.object(stream_metrics, "_stall_counter", stall),
    ):
        stream_metrics.record_stream_stall()

    assert stall.calls == [(1, None)]


class _FakeInstrument:
    """Records (value, attributes) for add()/record() so tests can assert on them."""

    def __init__(self):
        self.calls: list[tuple[float, dict | None]] = []

    def add(self, value, attributes=None):
        self.calls.append((value, attributes))

    def record(self, value, attributes=None):
        self.calls.append((value, attributes))


class _ExplodingInstrument:
    """Raises on every emission to prove the record_* functions swallow faults."""

    def add(self, value, attributes=None):
        raise OSError("instrument in a bad state")

    def record(self, value, attributes=None):
        raise OSError("instrument in a bad state")
