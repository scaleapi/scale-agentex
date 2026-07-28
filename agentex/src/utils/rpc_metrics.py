"""
Metrics for the agent JSON-RPC endpoint (``/agents/*/rpc``).

Recorded through the OpenTelemetry SDK when an OTLP endpoint is configured
(``OTEL_EXPORTER_OTLP_ENDPOINT``); when it isn't, every function here is a
cheap no-op. Unlike ``src/utils/db_metrics.py`` / ``src/utils/cache_metrics.py``
there is no StatsD dual-emit: these series are new, so nothing on the Datadog
side consumes them — OTel-only until a consumer appears.

Metric attributes follow the OTel RPC semantic conventions (``rpc.system``,
``rpc.method``, ``rpc.jsonrpc.error_code``, ``error.type``) plus ``streaming``.
High-cardinality identifiers (task id, agent id, request id) are deliberately
excluded from metric attributes; they belong on spans and logs only.

JSON-RPC status note: RPC-level failures return HTTP 200 with a ``JSONRPCError``
in the body, so failures carry ``rpc.jsonrpc.error_code`` (the JSON-RPC error
code, e.g. ``-32603``) rather than an HTTP status. Per the RPC semconv the
attribute is only set when the call failed; success omits it, and error rate is
read from the dedicated ``agentex.rpc.errors`` counter.

``task/create`` doubles as the workflow-level entry point for an agent
invocation, so it additionally emits ``gen_ai.workflow.duration`` labeled with
the OTel GenAI operation name (``invoke_workflow``) — workflow-level duration
stays directly queryable instead of being inferable only from RPC duration.
The GenAI semconv pairs ``gen_ai.workflow.duration`` with ``invoke_workflow``;
``invoke_agent`` is reserved for ``gen_ai.invoke_agent.duration``, which the
agent loop itself will emit — keeping the two operation names distinct means a
query on either name never mixes gateway workflow duration with in-pod agent
invocation duration. (These metrics are Development stability in the GenAI
semconv; names may still evolve upstream.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.utils.logging import make_logger
from src.utils.otel_metrics import get_meter

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram

logger = make_logger(__name__)

RPC_SYSTEM = "jsonrpc"

# Methods that mark the workflow-level entry point of an agent invocation, and
# the OTel GenAI operation name each one is recorded under. Only these methods
# emit ``gen_ai.workflow.duration``; the value must stay a bounded set of
# semconv-style operation names, never a per-request identifier.
WORKFLOW_OPERATION_BY_METHOD = {
    "task/create": "invoke_workflow",
}

# Bucket boundaries (seconds) for the request-duration histogram: the OTel HTTP
# semconv boundaries extended upward, because streaming responses are timed
# dispatch-to-final-byte and regularly run minutes. Without this advisory the
# SDK falls back to millisecond-scale default boundaries [0, 5, 10, 25, ...]
# and every sub-5-second observation lands in a single bucket.
_DURATION_BUCKET_BOUNDARIES_S = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
)

# Lazily-created OTel instruments (created once, on first use).
_duration_histogram: Histogram | None = None
_request_counter: Counter | None = None
_error_counter: Counter | None = None
_workflow_duration_histogram: Histogram | None = None
_instruments_initialized = False


def _ensure_instruments() -> None:
    """Create OTel instruments on first use. No-op if OTel is not configured."""
    global _duration_histogram, _request_counter, _error_counter
    global _workflow_duration_histogram
    global _instruments_initialized

    if _instruments_initialized:
        return
    _instruments_initialized = True

    meter = get_meter("agentex.rpc")
    if meter is None:
        # OTel not configured; nothing to emit to. Instruments stay None and
        # record_rpc_request degrades to just the completion log line.
        return

    _duration_histogram = meter.create_histogram(
        name="agentex.rpc.request.duration",
        description="Duration of agent JSON-RPC requests, from dispatch to final byte",
        unit="s",
        explicit_bucket_boundaries_advisory=_DURATION_BUCKET_BOUNDARIES_S,
    )
    _request_counter = meter.create_counter(
        name="agentex.rpc.requests",
        description="Agent JSON-RPC requests, tagged by method, status, and streaming",
        unit="{request}",
    )
    _error_counter = meter.create_counter(
        name="agentex.rpc.errors",
        description="Agent JSON-RPC requests that returned a JSONRPCError",
        unit="{error}",
    )
    _workflow_duration_histogram = meter.create_histogram(
        name="gen_ai.workflow.duration",
        description=(
            "Duration of the workflow-level agent invocation entry point, "
            "tagged with the GenAI operation name (e.g. invoke_workflow for "
            "task/create)"
        ),
        unit="s",
        explicit_bucket_boundaries_advisory=_DURATION_BUCKET_BOUNDARIES_S,
    )


def record_rpc_request(
    method: str,
    streaming: bool,
    duration_s: float,
    error_code: int | None = None,
    error_type: str | None = None,
) -> None:
    """
    Record one completed JSON-RPC request (successful or failed).

    Args:
        method: JSON-RPC method (e.g. "task/create", "message/send").
        streaming: Whether the response was streamed (NDJSON) or a single body.
        duration_s: Seconds from dispatch to completion. For streaming
            responses this covers the whole stream, not just the handler return.
        error_code: JSON-RPC error code (e.g. -32602) when the call failed;
            ``None`` on success. Sets the ``rpc.jsonrpc.error_code`` attribute
            and drives the error counter.
        error_type: Exception class name for failures; omitted on success.

    Never raises: emission failures (an OTel SDK fault) are swallowed so
    instrumentation can never disrupt the RPC path.
    """
    try:
        _ensure_instruments()

        failed = error_code is not None
        attributes: dict[str, str | bool | int] = {
            "rpc.system": RPC_SYSTEM,
            "rpc.method": method,
            "streaming": streaming,
        }
        # rpc.jsonrpc.error_code is set only on failure, per the RPC semconv.
        if error_code is not None:
            attributes["rpc.jsonrpc.error_code"] = error_code
        if error_type is not None:
            attributes["error.type"] = error_type

        if _duration_histogram is not None:
            _duration_histogram.record(duration_s, attributes)
        if _request_counter is not None:
            _request_counter.add(1, attributes)
        if _error_counter is not None and failed:
            _error_counter.add(1, attributes)

        workflow_operation = WORKFLOW_OPERATION_BY_METHOD.get(method)
        if workflow_operation is not None and _workflow_duration_histogram is not None:
            workflow_attributes: dict[str, str] = {
                "gen_ai.operation.name": workflow_operation,
            }
            if error_type is not None:
                workflow_attributes["error.type"] = error_type
            _workflow_duration_histogram.record(duration_s, workflow_attributes)

        # One structured completion line per RPC, carrying the terminal fields
        # the observability contract requires on logs (status, error.type,
        # duration_ms). rpc.method / agent.* / task.id ride along via the
        # per-request log-fields context (see add_log_fields).
        completion_fields: dict[str, str | bool | float] = {
            "rpc.method": method,
            "status": "ok" if error_code is None else str(error_code),
            "streaming": streaming,
            "duration_ms": round(duration_s * 1000.0, 3),
        }
        if error_type is not None:
            completion_fields["error.type"] = error_type
        logger.info("Agent RPC completed", extra=completion_fields)
    except Exception:
        logger.debug("Failed to emit agentex.rpc metrics", exc_info=True)
