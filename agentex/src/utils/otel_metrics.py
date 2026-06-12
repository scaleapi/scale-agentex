"""
OpenTelemetry bootstrap and custom metrics for Agentex.

Two responsibilities:

1. **Auto-instrumentation** — ``bootstrap_auto_instrumentation()`` runs at import
   (keep ``otel_metrics`` first in ``app.py``, before any auto-instrumented
   library) so ``initialize()`` executes in each uvicorn spawn worker when
   contrib packages are installed.

2. **Custom app metrics** — ``init_otel_metrics()`` registers Agentex instruments
   (``auth_cache_*``, ``db_*``, etc.). Attaches to an existing global
   ``MeterProvider`` from bootstrap/operator when present; otherwise creates a
   standalone OTLP pipeline when an endpoint is configured.

**Datadog ``ddtrace-run`` coexistence:** Neither OTel nor ddtrace detects the other's
FastAPI patches. If both run in one process, ddtrace wraps the middleware stack
first; OTel skips ``OpenTelemetryMiddleware`` with "unexpected middleware stack"
and HTTP OTel metrics/traces are not emitted. Helm avoids this by using
``ddtrace-run`` only when ``datadog.env`` is set (OTel-only otherwise). If both
are required, set ``DD_TRACE_FASTAPI_ENABLED=false`` and
``DD_TRACE_STARLETTE_ENABLED=false`` so OTel owns HTTP instrumentation.

**Per-worker ``service.instance.id``:** Uvicorn spawn workers share pod-level
``OTEL_RESOURCE_ATTRIBUTES``, so auto-instrumentation would otherwise emit all
workers on the same metric timeseries (see `OTel #4390
<https://github.com/open-telemetry/opentelemetry-python/issues/4390>`_).
``bootstrap_auto_instrumentation()`` appends ``.<pid>`` to ``service.instance.id``
in ``OTEL_RESOURCE_ATTRIBUTES`` before ``initialize()``; standalone
``init_otel_metrics()`` applies the same via ``Resource.merge``. With
``--workers 1``, operator ``sitecustomize`` may have already called
``initialize()``; bootstrap calls it again (OTel providers and instrumentors
are set-once; duplicate calls only produce log warnings).

Environment variables (custom metrics / standalone mode):
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Metrics endpoint (falls back to
        OTEL_EXPORTER_OTLP_ENDPOINT)
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL: Export protocol (falls back to
        OTEL_EXPORTER_OTLP_PROTOCOL; default: grpc)
    OTEL_EXPORTER_OTLP_ENDPOINT: General OTLP endpoint URL
    OTEL_EXPORTER_OTLP_HEADERS: Passed through by OTLP exporters when set
    OTEL_SERVICE_NAME: Service name (default: agentex)
    OTEL_METRICS_EXPORT_INTERVAL_MS: Export interval in ms (default: 30000)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from opentelemetry.sdk.resources import (
    OTELResourceDetector,
    Resource,
    get_aggregated_resources,
)

_auto_instrumentation_bootstrapped = False

_bootstrap_log = logging.getLogger(__name__)


def _unique_instance_id(resource: Resource) -> str:
    """Worker-unique service.instance.id (OTel #4390)."""
    pid = os.getpid()
    existing = resource.attributes.get("service.instance.id")
    if existing:
        existing = str(existing)
        suffix = f".{pid}"
        return existing if existing.endswith(suffix) else f"{existing}{suffix}"
    service = (
        resource.attributes.get("service.name")
        or os.environ.get("OTEL_SERVICE_NAME")
        or "unknown"
    )
    pod = resource.attributes.get("k8s.pod.name") or "unknown"
    return f"{service}.{pod}.{pid}"


def _resource_with_unique_instance_id() -> Resource:
    resource = get_aggregated_resources([OTELResourceDetector()])
    return resource.merge(
        Resource.create({"service.instance.id": _unique_instance_id(resource)})
    )


def _sync_instance_id_to_env(instance_id: str) -> None:
    """Write service.instance.id into OTEL_RESOURCE_ATTRIBUTES for auto-instrumentation."""
    key = "service.instance.id"
    parts = [
        part.strip()
        for part in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").split(",")
        if part.strip() and not part.strip().startswith(f"{key}=")
    ]
    parts.append(f"{key}={instance_id}")
    os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(parts)


def bootstrap_auto_instrumentation() -> bool:
    """Call ``initialize()`` once per process when auto-instrumentation is available.

    Import ``otel_metrics`` before any auto-instrumented library (FastAPI, httpx,
    SQLAlchemy, etc.) — instrumentors patch at import time. In ``app.py`` this
    must be the first import so bootstrap runs in each uvicorn spawn worker.

    Runs when: contrib packages are installed (no ``ImportError``).
    Skips when: already bootstrapped in this process, or packages absent.

    Export config, ``OTEL_SDK_DISABLED``, and disabled instrumentations are
    handled inside ``initialize()`` — not gated here. Custom app metrics use
    ``init_otel_metrics()`` separately.

    Returns:
        True if ``initialize()`` ran; False if skipped.
    """
    global _auto_instrumentation_bootstrapped

    if _auto_instrumentation_bootstrapped:
        return False
    _auto_instrumentation_bootstrapped = True

    try:
        from opentelemetry.instrumentation.auto_instrumentation import initialize
    except ImportError:
        return False

    _sync_instance_id_to_env(
        _unique_instance_id(get_aggregated_resources([OTELResourceDetector()]))
    )
    initialize()
    _bootstrap_log.debug(
        "OpenTelemetry auto-instrumentation bootstrapped (pid=%s)",
        os.getpid(),
    )
    return True


bootstrap_auto_instrumentation()

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as OTLPGrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as OTLPHttpMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION

from src.utils.logging import make_logger

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter
    from opentelemetry.sdk.metrics.export import MetricExporter

logger = make_logger(__name__)

# Global state
_meter_provider: MeterProvider | None = None # Set only when this module creates the provider
_initialized: bool = False

# Default configuration
DEFAULT_SERVICE_NAME = "agentex"
DEFAULT_EXPORT_INTERVAL_MS = 30000  # 30 seconds


def _global_meter_provider() -> MeterProvider | None:
    """Return the global MeterProvider if installed, else None (proxy is ignored)."""
    provider = metrics.get_meter_provider()
    return provider if isinstance(provider, MeterProvider) else None


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


def _create_metric_exporter(endpoint: str, protocol: str) -> MetricExporter:
    if protocol in {"http/protobuf", "http"}:
        return OTLPHttpMetricExporter(endpoint=endpoint)

    if protocol != "grpc":
        logger.warning("Unknown OTEL metrics protocol %r; using grpc", protocol)

    return OTLPGrpcMetricExporter(
        endpoint=endpoint,
        insecure=endpoint.startswith("http://"),
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

    If auto-instrumentation already installed a MeterProvider, custom metrics
    attach to it. Otherwise, initializes only when an OTLP endpoint is configured.

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

    if existing := _global_meter_provider():
        _initialized = True
        logger.info("OpenTelemetry metrics using existing MeterProvider")
        return existing

    endpoint = _metrics_endpoint(otlp_endpoint)
    if not endpoint:
        _initialized = True
        logger.info("OpenTelemetry metrics disabled: no OTLP endpoint configured")
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
    resource = _resource_with_unique_instance_id().merge(
        Resource.create(
            {
                SERVICE_NAME: resolved_service_name,
                SERVICE_VERSION: service_version
                or os.environ.get("SERVICE_VERSION", "0.1.0"),
                "deployment.environment": environment
                or os.environ.get("ENVIRONMENT", "development"),
            }
        )
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
    _meter_provider = provider
    _initialized = True
    logger.info(
        f"OpenTelemetry metrics initialized: endpoint={endpoint}, "
        f"protocol={protocol}, service={resolved_service_name}, "
        f"interval={resolved_export_interval_ms}ms"
    )
    return _meter_provider


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
