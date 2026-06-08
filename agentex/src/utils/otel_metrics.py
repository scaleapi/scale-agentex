"""
OpenTelemetry metrics configuration for Agentex.

When auto-instrumentation (e.g. OTel Operator) has already installed a global
MeterProvider, custom app metrics attach to it instead of replacing it.
Otherwise this module creates its own provider with OTLP export when an endpoint
is configured.

Environment Variables:
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Metrics OTLP endpoint (falls back to
        OTEL_EXPORTER_OTLP_ENDPOINT)
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL: Metrics export protocol (falls back to
        OTEL_EXPORTER_OTLP_PROTOCOL; default: grpc)
    OTEL_EXPORTER_OTLP_ENDPOINT: General OTLP endpoint URL
    OTEL_EXPORTER_OTLP_HEADERS: Optional headers for authentication
    OTEL_SERVICE_NAME: Service name for metrics (default: agentex)
    OTEL_METRICS_EXPORT_INTERVAL_MS: Export interval in ms (default: 30000)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as OTLPGrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as OTLPHttpMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource

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

    _initialized = True

    if existing := _global_meter_provider():
        logger.info("OpenTelemetry metrics using existing MeterProvider")
        return existing

    endpoint = _metrics_endpoint(otlp_endpoint)
    if not endpoint:
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
    resource = Resource.create(
        {
            SERVICE_NAME: resolved_service_name,
            SERVICE_VERSION: service_version
            or os.environ.get("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": environment
            or os.environ.get("ENVIRONMENT", "development"),
        }
    )
    reader = PeriodicExportingMetricReader(
        exporter=_create_metric_exporter(endpoint, protocol),
        export_interval_millis=resolved_export_interval_ms,
    )

    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)
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

    if _meter_provider is not None:
        _meter_provider.shutdown()
        logger.info("OpenTelemetry metrics shut down")

    _meter_provider = None
    _initialized = False


def is_otel_configured() -> bool:
    """Check if metrics export is configured via environment."""
    return bool(_metrics_endpoint())
