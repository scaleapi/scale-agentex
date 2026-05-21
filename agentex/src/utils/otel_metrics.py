"""
OpenTelemetry metrics configuration for Agentex.

This module sets up the OTel MeterProvider with OTLP export for metrics.
Metrics are exported to an OTLP-compatible endpoint (e.g., OTel Collector,
Datadog Agent, or directly to Grafana Cloud/Mimir).

Environment Variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL (default: http://localhost:4317)
    OTEL_EXPORTER_OTLP_HEADERS: Optional headers for authentication
    OTEL_SERVICE_NAME: Service name for metrics (default: agentex)
    OTEL_METRICS_EXPORT_INTERVAL_MS: Export interval in ms (default: 30000)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource

from src.utils.logging import make_logger

if TYPE_CHECKING:
    from opentelemetry.metrics import Meter

logger = make_logger(__name__)

# Global state
_meter_provider: MeterProvider | None = None
_initialized: bool = False

# Default configuration
DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"
DEFAULT_SERVICE_NAME = "agentex"
DEFAULT_EXPORT_INTERVAL_MS = 30000  # 30 seconds


def init_otel_metrics(
    service_name: str | None = None,
    service_version: str | None = None,
    environment: str | None = None,
    otlp_endpoint: str | None = None,
    export_interval_ms: int | None = None,
) -> MeterProvider | None:
    """
    Initialize OpenTelemetry metrics with OTLP exporter.

    This should be called once at application startup. Subsequent calls
    will return the existing MeterProvider.

    NOTE: Only initializes if OTEL_EXPORTER_OTLP_ENDPOINT is configured.
    Returns None if OTel is not configured.

    Args:
        service_name: Service name for resource attributes
        service_version: Service version for resource attributes
        environment: Deployment environment (e.g., "development", "production")
        otlp_endpoint: OTLP gRPC endpoint URL
        export_interval_ms: Metric export interval in milliseconds

    Returns:
        The configured MeterProvider, or None if not configured
    """
    global _meter_provider, _initialized

    if _initialized:
        return _meter_provider

    # Check if OTLP endpoint is configured
    otlp_endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.info(
            "OpenTelemetry metrics disabled: OTEL_EXPORTER_OTLP_ENDPOINT not configured"
        )
        _initialized = True
        return None

    # Resolve configuration from environment or defaults
    service_name = (
        service_name or os.environ.get("OTEL_SERVICE_NAME") or DEFAULT_SERVICE_NAME
    )
    service_version = service_version or os.environ.get("SERVICE_VERSION", "0.1.0")
    environment = environment or os.environ.get("ENVIRONMENT", "development")
    export_interval_ms = export_interval_ms or int(
        os.environ.get("OTEL_METRICS_EXPORT_INTERVAL_MS", DEFAULT_EXPORT_INTERVAL_MS)
    )

    # Create resource with service information
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": environment,
        }
    )

    # Create OTLP exporter
    # The exporter will use OTEL_EXPORTER_OTLP_HEADERS env var for auth if set
    exporter = OTLPMetricExporter(
        endpoint=otlp_endpoint,
        insecure=otlp_endpoint.startswith("http://"),  # Use insecure for non-TLS
    )

    # Create periodic reader that exports at the specified interval
    reader = PeriodicExportingMetricReader(
        exporter=exporter,
        export_interval_millis=export_interval_ms,
    )

    # Create and set the meter provider
    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[reader],
    )
    metrics.set_meter_provider(_meter_provider)

    _initialized = True
    logger.info(
        f"OpenTelemetry metrics initialized: endpoint={otlp_endpoint}, "
        f"service={service_name}, interval={export_interval_ms}ms"
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
    global _initialized, _meter_provider

    if not _initialized:
        # Auto-initialize with defaults if not already initialized
        init_otel_metrics()

    # Return None if OTel is not configured
    if _meter_provider is None:
        return None

    return metrics.get_meter(name, version)


def shutdown_otel_metrics() -> None:
    """
    Shutdown the meter provider, flushing any remaining metrics.

    Should be called during application shutdown.
    """
    global _meter_provider, _initialized

    if _meter_provider is not None:
        _meter_provider.shutdown()
        logger.info("OpenTelemetry metrics shut down")
        _meter_provider = None
        _initialized = False


def is_otel_configured() -> bool:
    """Check if an OTLP endpoint is configured via environment."""
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))
