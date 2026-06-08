"""Unit tests for OpenTelemetry metrics initialization and coexistence."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as OTLPGrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as OTLPHttpMetricExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from src.utils import otel_metrics


def _set_global_meter_provider(provider: object | None = None) -> None:
    """Test-only access to the global MeterProvider slot.

    Skips with a clear message if OTel SDK internals move. Pass ``None`` to
    install the no-op proxy (unset state).
    """
    try:
        if provider is None:
            provider = metrics._internal._ProxyMeterProvider()
        metrics._internal._METER_PROVIDER = provider
    except AttributeError as exc:
        pytest.skip(f"OpenTelemetry SDK internals changed: {exc}")


@pytest.fixture(autouse=True)
def reset_otel_metrics_state():
    """Reset module and global OTel state between tests."""
    saved_provider = metrics.get_meter_provider()
    otel_metrics.shutdown_otel_metrics()
    _set_global_meter_provider()

    yield

    otel_metrics.shutdown_otel_metrics()
    _set_global_meter_provider(saved_provider)


def _set_operator_provider() -> MeterProvider:
    provider = MeterProvider(resource=Resource.create({}))
    _set_global_meter_provider(provider)
    return provider


@pytest.mark.unit
def test_init_coexists_with_existing_meter_provider():
    operator_provider = _set_operator_provider()

    result = otel_metrics.init_otel_metrics()

    assert result is operator_provider
    assert metrics.get_meter_provider() is operator_provider
    assert otel_metrics._initialized is True
    assert otel_metrics._meter_provider is None

    meter = otel_metrics.get_meter("agentex.test")
    assert meter is not None


@pytest.mark.unit
def test_init_is_idempotent_in_shared_mode():
    operator_provider = _set_operator_provider()

    assert otel_metrics.init_otel_metrics() is operator_provider
    assert otel_metrics.init_otel_metrics() is operator_provider


@pytest.mark.unit
def test_init_does_not_shutdown_operator_provider():
    operator_provider = _set_operator_provider()
    otel_metrics.init_otel_metrics()

    otel_metrics.shutdown_otel_metrics()

    assert metrics.get_meter_provider() is operator_provider
    assert otel_metrics._initialized is False
    assert otel_metrics._meter_provider is None
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_init_after_shutdown_in_shared_mode():
    operator_provider = _set_operator_provider()

    otel_metrics.init_otel_metrics()
    otel_metrics.shutdown_otel_metrics()

    assert otel_metrics.init_otel_metrics() is operator_provider


@pytest.mark.unit
def test_init_creates_meter_provider_when_none_configured(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    result = otel_metrics.init_otel_metrics()

    assert isinstance(result, MeterProvider)
    assert otel_metrics._meter_provider is result
    assert otel_metrics._initialized is True
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_init_retries_after_provider_creation_failure(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    with patch.object(
        metrics, "set_meter_provider", side_effect=RuntimeError("blocked")
    ):
        with pytest.raises(RuntimeError):
            otel_metrics.init_otel_metrics()
        assert otel_metrics._initialized is False

    result = otel_metrics.init_otel_metrics()

    assert isinstance(result, MeterProvider)
    assert otel_metrics._initialized is True


@pytest.mark.unit
def test_init_disabled_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)

    result = otel_metrics.init_otel_metrics()

    assert result is None
    assert otel_metrics.get_meter("agentex.test") is None


@pytest.mark.unit
def test_shutdown_resets_state_when_disabled(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)

    otel_metrics.init_otel_metrics()
    otel_metrics.shutdown_otel_metrics()

    assert otel_metrics._initialized is False
    assert otel_metrics._meter_provider is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("protocol_env", "expected_exporter"),
    [
        ("grpc", OTLPGrpcMetricExporter),
        ("http/protobuf", OTLPHttpMetricExporter),
    ],
)
def test_protocol_selection_from_env(
    monkeypatch, protocol_env: str, expected_exporter: type
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", protocol_env)

    with patch.object(otel_metrics, "_create_metric_exporter") as mock_create:
        mock_create.return_value = expected_exporter(endpoint="http://localhost:4318")
        otel_metrics.init_otel_metrics()

    mock_create.assert_called_once_with("http://localhost:4318", protocol_env)


@pytest.mark.unit
def test_metrics_endpoint_takes_precedence_over_general_endpoint(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://general:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://metrics:4318")

    with patch.object(otel_metrics, "_create_metric_exporter") as mock_create:
        mock_create.return_value = OTLPGrpcMetricExporter(
            endpoint="http://metrics:4318"
        )
        otel_metrics.init_otel_metrics()

    mock_create.assert_called_once_with("http://metrics:4318", "grpc")


@pytest.mark.unit
def test_init_after_shutdown_in_standalone_mode(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    first = otel_metrics.init_otel_metrics()
    assert first is not None
    otel_metrics.shutdown_otel_metrics()

    second = otel_metrics.init_otel_metrics()
    assert second is not None
    assert second is not first
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_shutdown_only_own_provider(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = otel_metrics.init_otel_metrics()
    assert provider is not None

    otel_metrics.shutdown_otel_metrics()

    assert otel_metrics._initialized is False
    assert otel_metrics._meter_provider is None
