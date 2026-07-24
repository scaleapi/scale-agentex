"""Tests for the agent RPC metrics emitter.

Same operational contract as the other metric emitters: the unconfigured path
must be a harmless no-op, emission failures must never propagate into the RPC
path, and the configured path must record the expected names and attributes.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from src.utils import rpc_metrics


def _patched_instruments(stack: ExitStack, **overrides):
    """Patch module state so record_rpc_request runs against controlled instruments.

    Defaults to everything disabled (OTel unconfigured); pass instrument mocks
    to enable a path.
    """
    state = {
        "_instruments_initialized": True,
        "_duration_histogram": None,
        "_request_counter": None,
        "_error_counter": None,
    }
    state.update(overrides)
    for name, value in state.items():
        stack.enter_context(patch.object(rpc_metrics, name, value))


@pytest.mark.unit
def test_record_rpc_request_is_noop_when_unconfigured():
    # With no OTLP endpoint configured, the call must be harmless.
    with ExitStack() as stack:
        _patched_instruments(stack)
        rpc_metrics.record_rpc_request(
            method="message/send", streaming=True, duration_s=1.5
        )


@pytest.mark.unit
def test_record_rpc_request_swallows_emission_errors():
    # A failing backend must never propagate into the RPC path.
    with ExitStack() as stack:
        histogram = MagicMock()
        histogram.record.side_effect = RuntimeError("SDK in a bad state")
        _patched_instruments(stack, _duration_histogram=histogram)

        rpc_metrics.record_rpc_request(
            method="task/create", streaming=False, duration_s=0.2
        )


@pytest.mark.unit
def test_otel_emission_names_and_attributes():
    with ExitStack() as stack:
        histogram = MagicMock()
        requests = MagicMock()
        errors = MagicMock()
        _patched_instruments(
            stack,
            _duration_histogram=histogram,
            _request_counter=requests,
            _error_counter=errors,
        )
        rpc_metrics.record_rpc_request(
            method="message/send", streaming=True, duration_s=2.0
        )

    expected_attributes = {
        "rpc.system.name": "jsonrpc",
        "rpc.method": "message/send",
        "rpc.response.status_code": "ok",
        "streaming": True,
    }
    # Duration is recorded in seconds on the OTel side.
    histogram.record.assert_called_once_with(2.0, expected_attributes)
    requests.add.assert_called_once_with(1, expected_attributes)
    errors.add.assert_not_called()


@pytest.mark.unit
def test_error_counter_on_failure():
    with ExitStack() as stack:
        requests = MagicMock()
        errors = MagicMock()
        _patched_instruments(stack, _request_counter=requests, _error_counter=errors)
        rpc_metrics.record_rpc_request(
            method="message/send",
            streaming=False,
            duration_s=0.4,
            status_code="-32603",
            error_type="ValueError",
        )

    expected_attributes = {
        "rpc.system.name": "jsonrpc",
        "rpc.method": "message/send",
        "rpc.response.status_code": "-32603",
        "streaming": False,
        "error.type": "ValueError",
    }
    requests.add.assert_called_once_with(1, expected_attributes)
    errors.add.assert_called_once_with(1, expected_attributes)
