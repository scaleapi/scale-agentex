"""
OpenTelemetry metrics configuration for Agentex.

The Python OTel SDK exposes a single global MeterProvider (set once). This module
uses two deterministic paths:

1. **Coexistence** — a real SDK MeterProvider is already global (e.g. from OTel
   Operator auto-instrumentation). Custom app metrics attach via get_meter();
   set_meter_provider() is never called.
2. **Standalone** — global is still the SDK proxy and an OTLP endpoint is
   configured. This module creates the first MeterProvider. Auto-instrumentation
   and custom metrics then share that same global slot.

Environment Variables:
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Metrics OTLP endpoint (falls back to
        OTEL_EXPORTER_OTLP_ENDPOINT)
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL: Metrics export protocol (falls back to
        OTEL_EXPORTER_OTLP_PROTOCOL; default: grpc)
    OTEL_EXPORTER_OTLP_ENDPOINT: General OTLP endpoint URL
    OTEL_EXPORTER_OTLP_HEADERS: Optional headers for authentication
    OTEL_SERVICE_NAME: Service name for metrics (default: agentex)
    OTEL_METRICS_EXPORT_INTERVAL_MS: Export interval in ms (default: 30000)
    OTEL_RESOURCE_ATTRIBUTES: K8s and service resource attrs (injected by the OTel
        Operator on cluster pods; read via OTELResourceDetector). Per-process
        service.instance.id is applied via Resource.merge when this module creates
        the MeterProvider; env is not modified.
    AGENTEX_OTEL_HTTP_METRICS_ENABLED: Opt-in in-process FastAPI HTTP metrics
        (default: false). When true, also set
        OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=fastapi,system_metrics on the pod
        so the OTel Operator does not double-instrument FastAPI.
    OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: Pod env; must include ``fastapi`` when
        using in-process HTTP metrics (see above).
    DD_TRACE_FASTAPI_ENABLED: Set to ``false`` when using ddtrace-run so ddtrace
        does not claim FastAPI before OpenTelemetry instrumentation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as OTLPGrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as OTLPHttpMetricExporter,
)
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider, UpDownCounter
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import (
    OTELResourceDetector,
    Resource,
    get_aggregated_resources,
)

from src.utils.logging import make_logger

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.sdk.metrics.export import MetricExporter

logger = make_logger(__name__)

# Global state
_meter_provider: MeterProvider | None = None  # Set only when this module creates the provider
_initialized: bool = False

# Default configuration
DEFAULT_SERVICE_NAME = "agentex"
DEFAULT_EXPORT_INTERVAL_MS = 30000  # 30 seconds

# Cumulative export is required for Prometheus/Mimir rate()/increase() on OTLP histograms.
# Delta temporality produces inflated or ramping RPS when queried via histogram_count(rate(...)).
_PREFERRED_OTLP_TEMPORALITY = {
    Counter: AggregationTemporality.CUMULATIVE,
    Histogram: AggregationTemporality.CUMULATIVE,
    UpDownCounter: AggregationTemporality.CUMULATIVE,
}


def _per_process_instance_id(resource: Resource) -> str:
    """Return a worker-unique service.instance.id from detected resource attrs."""
    pid = os.getpid()
    existing = resource.attributes.get("service.instance.id")
    if existing:
        existing = str(existing)
        pid_token = f".{pid}"
        if existing.endswith(pid_token) or f"{pid_token}." in existing:
            return existing
        return f"{existing}.{pid}"
    service = (
        resource.attributes.get("service.name")
        or os.environ.get("OTEL_SERVICE_NAME")
        or "unknown"
    )
    pod = resource.attributes.get("k8s.pod.name") or "unknown"
    return f"{service}.{pod}.{pid}"


def _build_resource() -> Resource:
    """Detect operator/k8s attrs from env; set a per-process service.instance.id."""
    resource = get_aggregated_resources([OTELResourceDetector()])
    service_instance_id = _per_process_instance_id(resource)
    return resource.merge(Resource.create({"service.instance.id": service_instance_id}))


def _global_meter_provider() -> MeterProvider | None:
    """Return the global MeterProvider if installed, else None (proxy is ignored)."""
    provider = metrics.get_meter_provider()
    return provider if isinstance(provider, MeterProvider) else None


def _describe_global_provider() -> tuple[str, bool]:
    provider = metrics.get_meter_provider()
    return type(provider).__name__, isinstance(provider, MeterProvider)


def _log_provider_state(
    message: str,
    *,
    app_provider: MeterProvider | None = None,
    mode: str | None = None,
) -> None:
    """Emit a single structured INFO log for operator/app coexistence debugging."""
    global_type, global_is_sdk = _describe_global_provider()
    global_provider = _global_meter_provider()
    app_owns_global = (
        app_provider is not None
        and global_provider is not None
        and global_provider is app_provider
    )
    parts = [
        message,
        f"mode={mode or 'unknown'}",
        f"global_type={global_type}",
        f"global_is_sdk_meter_provider={global_is_sdk}",
        f"app_owns_global={app_owns_global}",
    ]
    logger.info(", ".join(parts))


def _metrics_endpoint(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    return os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )


def _metrics_protocol() -> str:
    return (
        (
            os.environ.get("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL")
            or os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
        )
        .strip()
        .lower()
    )


def _http_metrics_export_url(endpoint: str) -> str:
    """Return an OTLP HTTP metrics URL including the /v1/metrics path.

    OTLPHttpMetricExporter only appends that path when it resolves the endpoint
    from environment variables, not when an explicit endpoint argument is passed.
    """
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/v1/metrics"):
        return normalized
    return f"{normalized}/v1/metrics"


def _create_metric_exporter(endpoint: str, protocol: str) -> MetricExporter:
    if protocol in {"http/protobuf", "http"}:
        return OTLPHttpMetricExporter(
            endpoint=_http_metrics_export_url(endpoint),
            preferred_temporality=_PREFERRED_OTLP_TEMPORALITY,
        )

    if protocol != "grpc":
        logger.warning("Unknown OTEL metrics protocol %r; using grpc", protocol)

    return OTLPGrpcMetricExporter(
        endpoint=endpoint,
        insecure=endpoint.startswith("http://"),
        preferred_temporality=_PREFERRED_OTLP_TEMPORALITY,
    )


def init_otel_metrics(
    service_name: str | None = None,
    service_version: str | None = None,
    environment: str | None = None,
    otlp_endpoint: str | None = None,
    export_interval_ms: int | None = None,
) -> MeterProvider | None:
    """
    Initialize OpenTelemetry metrics for custom app instruments.

    Call once at application startup. Subsequent calls return the active provider
    without re-initializing.

    If a real SDK MeterProvider is already global, custom metrics attach to it
    and set_meter_provider() is never called. Otherwise, when an OTLP endpoint
    is configured, this module installs the first global provider.

    Args:
        service_name: Service name for resource attributes
        service_version: Service version for resource attributes
        environment: Deployment environment (e.g., "development", "production")
        otlp_endpoint: OTLP endpoint URL
        export_interval_ms: Metric export interval in milliseconds

    Returns:
        The active MeterProvider, or None when metrics are disabled
    """
    global _meter_provider, _initialized

    if _initialized:
        return _meter_provider or _global_meter_provider()

    _log_provider_state("OpenTelemetry metrics init starting", mode="starting")

    if existing := _global_meter_provider():
        _initialized = True
        _log_provider_state(
            "OpenTelemetry metrics using existing MeterProvider",
            mode="coexistence",
        )
        return existing

    endpoint = _metrics_endpoint(otlp_endpoint)
    if not endpoint:
        _initialized = True
        _log_provider_state(
            "OpenTelemetry metrics disabled: no OTLP endpoint configured",
            mode="disabled",
        )
        return None

    protocol = _metrics_protocol()
    resolved_service_name = service_name or os.environ.get(
        "OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME
    )
    resolved_export_interval_ms = (
        export_interval_ms
        if export_interval_ms is not None
        else int(
            os.environ.get(
                "OTEL_METRICS_EXPORT_INTERVAL_MS", DEFAULT_EXPORT_INTERVAL_MS
            )
        )
    )
    resource = _build_resource()
    if not resource.attributes.get("k8s.pod.name"):
        logger.warning(
            "k8s.pod.name not set on MeterProvider resource; "
            "ensure OTEL_RESOURCE_ATTRIBUTES is injected (OTel Operator)."
        )
    reader = PeriodicExportingMetricReader(
        exporter=_create_metric_exporter(endpoint, protocol),
        export_interval_millis=resolved_export_interval_ms,
    )

    provider = MeterProvider(resource=resource, metric_readers=[reader])
    try:
        metrics.set_meter_provider(provider)
    except Exception:
        provider.shutdown()
        raise

    global_provider = _global_meter_provider()
    if global_provider is provider:
        _meter_provider = provider
        _initialized = True
        _log_provider_state(
            "OpenTelemetry metrics standalone init installed global MeterProvider: "
            f"endpoint={endpoint}, protocol={protocol}, service={resolved_service_name}, "
            f"interval={resolved_export_interval_ms}ms",
            app_provider=provider,
            mode="standalone",
        )
        return _meter_provider

    # set_meter_provider() was rejected; shut down the orphan to avoid background export noise.
    provider.shutdown()
    _initialized = True
    _log_provider_state(
        "OpenTelemetry metrics standalone set_meter_provider rejected; "
        "using existing global MeterProvider",
        app_provider=provider,
        mode="standalone_rejected",
    )
    return global_provider


def get_meter(name: str, version: str = "0.1.0") -> Meter | None:
    """
    Get a meter for instrumenting a component.

    Args:
        name: The name of the instrumentation scope (e.g., "db_metrics")
        version: The version of the instrumentation

    Returns:
        An OpenTelemetry Meter instance, or None if OTel is not configured
    """
    if not _initialized:
        init_otel_metrics()
    if _meter_provider is None and _global_meter_provider() is None:
        return None
    return metrics.get_meter(name, version)


def shutdown_otel_metrics() -> None:
    """
    Shutdown the meter provider, flushing any remaining metrics.

    Should be called during application shutdown. Only shuts down a provider
    this module created; a provider installed by auto-instrumentation is left
    running.
    """
    global _meter_provider, _initialized

    try:
        if _meter_provider is not None:
            _meter_provider.shutdown()
            logger.info("OpenTelemetry metrics shut down")
    except Exception:
        logger.exception("OpenTelemetry metrics shutdown failed")
    finally:
        _meter_provider = None
        _initialized = False


def is_otel_configured() -> bool:
    """Check if metrics export is configured via environment."""
    return bool(_metrics_endpoint())


def _http_metrics_enabled() -> bool:
    """Return whether in-process FastAPI HTTP metrics should be installed."""
    flag = os.environ.get("AGENTEX_OTEL_HTTP_METRICS_ENABLED", "false").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def instrument_fastapi_http_metrics(app: Any) -> bool:
    """
    Install in-process FastAPI HTTP server metrics (http.server.request.duration).

    Prefer :func:`configure_app_metrics`. When called directly, invoke before the
    ASGI server handles any messages (lifespan startup is too late).

    Requires ``AGENTEX_OTEL_HTTP_METRICS_ENABLED=true`` and
    ``OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=fastapi,system_metrics`` on the pod.

    Returns:
        True when instrumentation was applied, False when skipped or disabled.
    """
    if not _http_metrics_enabled():
        logger.info("FastAPI HTTP metrics disabled via AGENTEX_OTEL_HTTP_METRICS_ENABLED")
        return False

    if getattr(app, "_is_instrumented_by_opentelemetry", False):
        logger.info(
            "FastAPI already instrumented by OpenTelemetry; skipping in-process HTTP metrics"
        )
        return False

    if not _initialized:
        init_otel_metrics()

    if _global_meter_provider() is None and not is_otel_configured():
        logger.info(
            "FastAPI HTTP metrics skipped: no MeterProvider and no OTLP endpoint configured"
        )
        return False

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    meter_provider = _global_meter_provider()
    FastAPIInstrumentor.instrument_app(app, meter_provider=meter_provider)
    logger.info("FastAPI in-process HTTP metrics instrumentation enabled")
    return True


def configure_app_metrics(app: Any) -> None:
    """
    Initialize OTLP metrics and optional FastAPI HTTP instrumentation.

    Call once at module import after the FastAPI app is fully configured (middleware,
    routes, handlers) and before wrapping it or serving any ASGI messages.
    Lifespan is too late: Starlette caches ``middleware_stack`` on the first ASGI
    message (usually lifespan startup), before the lifespan handler runs.

    HTTP metrics are opt-in via ``AGENTEX_OTEL_HTTP_METRICS_ENABLED`` (default false).
    Beyla/eBPF HTTP metrics are independent and use different label sets when present.
    """
    init_otel_metrics()
    if not _http_metrics_enabled():
        return
    if not instrument_fastapi_http_metrics(app):
        logger.warning(
            "FastAPI HTTP metrics were not applied despite "
            "AGENTEX_OTEL_HTTP_METRICS_ENABLED; see prior log lines for the skip reason"
        )
