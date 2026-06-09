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
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from src.utils import cache_metrics, otel_metrics


def _set_global_meter_provider(provider: object | None = None) -> None:
    """Test-only access to the global MeterProvider slot.

    Skips with a clear message if OTel SDK internals move. Pass ``None`` to
    install the no-op proxy (unset state).
    """
    try:
        from opentelemetry.util._once import Once

        if provider is None:
            provider = metrics._internal._ProxyMeterProvider()
        metrics._internal._METER_PROVIDER = provider
        metrics._internal._METER_PROVIDER_SET_ONCE = Once()
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


def _enable_auto_instrumentation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "otlp")
    monkeypatch.setenv(
        "PYTHONPATH",
        "/otel-auto-instrumentation-python/opentelemetry/instrumentation/auto_instrumentation",
    )


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
def test_init_creates_standalone_when_operator_env_but_proxy_global(monkeypatch):
    """Operator injection env must not block first-setter standalone on proxy."""
    _enable_auto_instrumentation_env(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

    result = otel_metrics.init_otel_metrics()

    assert isinstance(result, MeterProvider)
    assert otel_metrics._meter_provider is result
    assert metrics.get_meter_provider() is result
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_init_creates_meter_provider_when_none_configured(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    result = otel_metrics.init_otel_metrics()

    assert isinstance(result, MeterProvider)
    assert otel_metrics._meter_provider is result
    assert otel_metrics._initialized is True
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_init_coexists_without_set_meter_provider_when_operator_present(
    monkeypatch,
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    operator_provider = _set_operator_provider()

    with patch.object(metrics, "set_meter_provider") as mock_set:
        result = otel_metrics.init_otel_metrics()

    mock_set.assert_not_called()
    assert result is operator_provider
    assert metrics.get_meter_provider() is operator_provider
    assert otel_metrics._meter_provider is None
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_standalone_shuts_down_orphan_when_set_meter_provider_rejected(
    monkeypatch,
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    preexisting = MeterProvider(resource=Resource.create({}))
    real_set = metrics.set_meter_provider

    def racing_set(provider: MeterProvider) -> None:
        if not isinstance(metrics.get_meter_provider(), MeterProvider):
            real_set(preexisting)
        real_set(provider)

    with patch.object(metrics, "set_meter_provider", side_effect=racing_set):
        result = otel_metrics.init_otel_metrics()

    assert result is preexisting
    assert metrics.get_meter_provider() is preexisting
    assert otel_metrics._meter_provider is None
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_init_retries_after_provider_creation_failure(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    with (
        patch.object(
            metrics, "set_meter_provider", side_effect=RuntimeError("blocked")
        ),
        patch.object(MeterProvider, "shutdown") as mock_shutdown,
    ):
        with pytest.raises(RuntimeError):
            otel_metrics.init_otel_metrics()
        assert otel_metrics._initialized is False
        mock_shutdown.assert_called_once()

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
def test_custom_metrics_preserve_instrument_attributes_in_shared_mode():
    """Instrument names and point attributes must not change when attaching to operator provider."""
    cache_metrics._instruments_initialized = False
    cache_metrics._access_counter = None
    cache_metrics._eviction_counter = None

    reader = InMemoryMetricReader()
    operator_provider = MeterProvider(
        resource=Resource.create({"service.name": "operator-svc"}),
        metric_readers=[reader],
    )
    _set_global_meter_provider(operator_provider)

    otel_metrics.init_otel_metrics()
    cache_metrics.record_cache_access("auth_gateway", "hit")
    cache_metrics.record_cache_eviction("agent_api_key")

    data = reader.get_metrics_data()
    assert data is not None
    points = [
        (
            metric.name,
            scope.scope.name,
            dict(data_point.attributes),
        )
        for resource_metrics in data.resource_metrics
        for scope in resource_metrics.scope_metrics
        for metric in scope.metrics
        for data_point in metric.data.data_points
    ]
    assert (
        "auth_cache.access",
        "agentex.auth_cache",
        {"cache": "auth_gateway", "result": "hit"},
    ) in points
    assert (
        "auth_cache.eviction",
        "agentex.auth_cache",
        {"cache": "agent_api_key"},
    ) in points


@pytest.mark.unit
@pytest.mark.parametrize(
    ("input_endpoint", "expected_url"),
    [
        ("http://collector:4318", "http://collector:4318/v1/metrics"),
        (
            "http://collector:4318/v1/metrics",
            "http://collector:4318/v1/metrics",
        ),
    ],
)
def test_http_metrics_export_url(input_endpoint: str, expected_url: str):
    assert otel_metrics._http_metrics_export_url(input_endpoint) == expected_url


@pytest.mark.unit
def test_create_http_metric_exporter_uses_v1_metrics_path():
    exporter = otel_metrics._create_metric_exporter(
        "http://collector:4318", "http/protobuf"
    )

    assert isinstance(exporter, OTLPHttpMetricExporter)
    assert exporter._endpoint == "http://collector:4318/v1/metrics"


@pytest.mark.unit
def test_init_after_shutdown_in_standalone_mode(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    first = otel_metrics.init_otel_metrics()
    assert first is not None
    otel_metrics.shutdown_otel_metrics()

    second = otel_metrics.init_otel_metrics()
    assert second is not None
    assert second is first
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_shutdown_resets_state_when_provider_shutdown_raises(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = otel_metrics.init_otel_metrics()
    assert provider is not None

    with patch.object(provider, "shutdown", side_effect=RuntimeError("export failed")):
        otel_metrics.shutdown_otel_metrics()

    assert otel_metrics._initialized is False
    assert otel_metrics._meter_provider is None
    assert otel_metrics.init_otel_metrics() is not None


@pytest.mark.unit
def test_shutdown_only_own_provider(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = otel_metrics.init_otel_metrics()
    assert provider is not None

    otel_metrics.shutdown_otel_metrics()

    assert otel_metrics._initialized is False
    assert otel_metrics._meter_provider is None


@pytest.mark.unit
def test_instrument_fastapi_skips_when_disabled_by_default(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.delenv("AGENTEX_OTEL_HTTP_METRICS_ENABLED", raising=False)

    app = FastAPI()
    assert otel_metrics.instrument_fastapi_http_metrics(app) is False


@pytest.mark.unit
def test_instrument_fastapi_skips_when_already_instrumented(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setenv("AGENTEX_OTEL_HTTP_METRICS_ENABLED", "true")

    app = FastAPI()
    app._is_instrumented_by_opentelemetry = True  # noqa: SLF001

    assert otel_metrics.instrument_fastapi_http_metrics(app) is False


@pytest.mark.unit
def test_instrument_fastapi_skips_without_otel_config(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setenv("AGENTEX_OTEL_HTTP_METRICS_ENABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)

    app = FastAPI()
    assert otel_metrics.instrument_fastapi_http_metrics(app) is False


@pytest.mark.unit
def test_instrument_fastapi_applies_with_existing_provider(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AGENTEX_OTEL_HTTP_METRICS_ENABLED", "true")
    monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

    reader = InMemoryMetricReader()
    provider = MeterProvider(
        resource=Resource.create({"service.name": "agentex"}),
        metric_readers=[reader],
    )
    _set_global_meter_provider(provider)
    otel_metrics.init_otel_metrics()

    app = FastAPI()

    @app.get("/probe")
    def probe() -> dict[str, str]:
        return {"ok": "true"}

    assert otel_metrics.instrument_fastapi_http_metrics(app) is True
    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is True

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 200

    data = reader.get_metrics_data()
    assert data is not None
    metric_names = {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope in resource_metrics.scope_metrics
        for metric in scope.metrics
    }
    assert "http.server.request.duration" in metric_names


@pytest.mark.unit
def test_instrument_fastapi_is_idempotent(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setenv("AGENTEX_OTEL_HTTP_METRICS_ENABLED", "true")

    _set_operator_provider()
    otel_metrics.init_otel_metrics()
    app = FastAPI()

    assert otel_metrics.instrument_fastapi_http_metrics(app) is True
    assert otel_metrics.instrument_fastapi_http_metrics(app) is False
