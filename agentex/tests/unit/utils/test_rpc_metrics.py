"""Tests for the agent RPC metrics emitter.

Same operational contract as the other metric emitters: the unconfigured path
must be a harmless no-op, emission failures must never propagate into the RPC
path, and the configured path must record the expected names and attributes.
Also covers the workflow-level GenAI histogram, which only workflow
entry-point methods (task/create) may emit.
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
        "_workflow_duration_histogram": None,
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
        "rpc.system": "jsonrpc",
        "rpc.method": "message/send",
        "streaming": True,
    }
    # Duration is recorded in seconds on the OTel side. Success omits
    # rpc.jsonrpc.error_code, per the RPC semconv.
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
            error_code=-32603,
            error_type="ValueError",
        )

    expected_attributes = {
        "rpc.system": "jsonrpc",
        "rpc.method": "message/send",
        "rpc.jsonrpc.error_code": -32603,
        "streaming": False,
        "error.type": "ValueError",
    }
    requests.add.assert_called_once_with(1, expected_attributes)
    errors.add.assert_called_once_with(1, expected_attributes)


@pytest.mark.unit
def test_otel_workflow_histogram_for_task_create():
    workflow_histogram = MagicMock()
    with ExitStack() as stack:
        _patched_instruments(stack, _workflow_duration_histogram=workflow_histogram)
        rpc_metrics.record_rpc_request(
            method="task/create", streaming=False, duration_s=0.5
        )

    workflow_histogram.record.assert_called_once_with(
        0.5, {"gen_ai.operation.name": "invoke_workflow"}
    )


@pytest.mark.unit
def test_otel_workflow_histogram_records_error_type_on_failure():
    workflow_histogram = MagicMock()
    with ExitStack() as stack:
        _patched_instruments(stack, _workflow_duration_histogram=workflow_histogram)
        rpc_metrics.record_rpc_request(
            method="task/create",
            streaming=False,
            duration_s=0.3,
            error_code=-32603,
            error_type="ValueError",
        )

    workflow_histogram.record.assert_called_once_with(
        0.3,
        {"gen_ai.operation.name": "invoke_workflow", "error.type": "ValueError"},
    )


@pytest.mark.unit
def test_otel_workflow_histogram_not_recorded_for_non_workflow_method():
    workflow_histogram = MagicMock()
    with ExitStack() as stack:
        _patched_instruments(stack, _workflow_duration_histogram=workflow_histogram)
        rpc_metrics.record_rpc_request(
            method="message/send", streaming=True, duration_s=0.1
        )

    workflow_histogram.record.assert_not_called()


@pytest.mark.unit
def test_timing_success_records_exactly_once_with_no_error():
    with patch.object(rpc_metrics, "record_rpc_request") as record:
        with rpc_metrics.rpc_request_timing("task/create", streaming=False):
            pass

    record.assert_called_once()
    kwargs = record.call_args.kwargs
    assert kwargs["method"] == "task/create"
    assert kwargs["streaming"] is False
    assert kwargs["error_code"] is None
    assert kwargs["error_type"] is None
    assert kwargs["duration_s"] >= 0


@pytest.mark.unit
def test_timing_handler_classified_failure_records_exactly_once():
    # The double-count regression: a handler that converts an exception into a
    # JSONRPCError response (and returns normally) must produce ONE record
    # carrying the error code — not one success and one failure.
    with patch.object(rpc_metrics, "record_rpc_request") as record:
        with rpc_metrics.rpc_request_timing("task/create", streaming=False) as rpc_call:
            rpc_call.fail(-32602, ValueError("bad params"))

    record.assert_called_once()
    kwargs = record.call_args.kwargs
    assert kwargs["error_code"] == -32602
    assert kwargs["error_type"] == "ValueError"


@pytest.mark.unit
def test_timing_escaping_exception_sets_error_type_and_reraises():
    with patch.object(rpc_metrics, "record_rpc_request") as record:
        with pytest.raises(RuntimeError):
            with rpc_metrics.rpc_request_timing("message/send", streaming=False):
                raise RuntimeError("handler blew up unclassified")

    record.assert_called_once()
    kwargs = record.call_args.kwargs
    assert kwargs["error_code"] is None
    assert kwargs["error_type"] == "RuntimeError"


@pytest.mark.unit
def test_timing_client_disconnect_is_not_a_success_and_not_an_rpc_error():
    # GeneratorExit is what a streaming generator sees when the client
    # disconnects mid-response: no error frame was delivered (error_code stays
    # None, so agentex.rpc.errors is untouched), but error.type must mark the
    # call so truncated streams don't read as clean successes.
    with patch.object(rpc_metrics, "record_rpc_request") as record:
        with pytest.raises(GeneratorExit):
            with rpc_metrics.rpc_request_timing("message/send", streaming=True):
                raise GeneratorExit()

    record.assert_called_once()
    kwargs = record.call_args.kwargs
    assert kwargs["error_code"] is None
    assert kwargs["error_type"] == "GeneratorExit"


@pytest.mark.unit
def test_timing_keeps_handler_classification_when_error_frame_delivery_dies():
    # A handler classifies a failure, then the yield of the error frame itself
    # dies (client already gone). The classified code must win — still exactly
    # one record.
    with patch.object(rpc_metrics, "record_rpc_request") as record:
        with pytest.raises(GeneratorExit):
            with rpc_metrics.rpc_request_timing(
                "message/send", streaming=True
            ) as rpc_call:
                rpc_call.fail(-32603, ValueError("upstream error"))
                raise GeneratorExit()

    record.assert_called_once()
    kwargs = record.call_args.kwargs
    assert kwargs["error_code"] == -32603
    assert kwargs["error_type"] == "ValueError"
