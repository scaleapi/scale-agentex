"""Unit tests for OpenTelemetry metrics initialization and coexistence."""

from __future__ import annotations

import os
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
from opentelemetry.sdk.resources import OTELResourceDetector, Resource, get_aggregated_resources
from src.utils import otel_metrics
from src.utils import cache_metrics


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
    saved_bootstrap = otel_metrics._auto_instrumentation_bootstrapped
    otel_metrics.shutdown_otel_metrics()
    otel_metrics._auto_instrumentation_bootstrapped = False
    _set_global_meter_provider()

    yield

    otel_metrics.shutdown_otel_metrics()
    otel_metrics._auto_instrumentation_bootstrapped = saved_bootstrap
    _set_global_meter_provider(saved_provider)


@pytest.mark.unit
def test_bootstrap_skips_when_auto_instrumentation_not_installed(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry.instrumentation.auto_instrumentation":
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        assert otel_metrics.bootstrap_auto_instrumentation() is False


@pytest.mark.unit
def test_bootstrap_runs_without_otlp_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("OTEL_EXPORTER_OTLP") and key.endswith("_ENDPOINT"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    with patch(
        "opentelemetry.instrumentation.auto_instrumentation.initialize"
    ) as initialize:
        assert otel_metrics.bootstrap_auto_instrumentation() is True
        initialize.assert_called_once()


@pytest.mark.unit
def test_bootstrap_calls_initialize_when_packages_available(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    with (
        patch.object(otel_metrics, "_sync_instance_id_to_env") as sync_env,
        patch(
            "opentelemetry.instrumentation.auto_instrumentation.initialize"
        ) as initialize,
    ):
        assert otel_metrics.bootstrap_auto_instrumentation() is True
        sync_env.assert_called_once()
        initialize.assert_called_once()
        assert otel_metrics.bootstrap_auto_instrumentation() is False


@pytest.mark.unit
def test_unique_instance_id_extends_operator_value(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agentex")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "k8s.pod.name=my-pod,service.instance.id=agentex.my-pod.agentex",
    )
    monkeypatch.setattr(otel_metrics.os, "getpid", lambda: 42)
    base = get_aggregated_resources([OTELResourceDetector()])
    assert otel_metrics._unique_instance_id(base) == "agentex.my-pod.agentex.42"


@pytest.mark.unit
def test_unique_instance_id_builds_when_missing(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agentex")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "k8s.pod.name=my-pod")
    monkeypatch.setattr(otel_metrics.os, "getpid", lambda: 42)
    base = get_aggregated_resources([OTELResourceDetector()])
    assert otel_metrics._unique_instance_id(base) == "agentex.my-pod.42"


@pytest.mark.unit
def test_resource_with_unique_instance_id_does_not_mutate_env(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agentex")
    original = "k8s.pod.name=my-pod,service.instance.id=agentex.my-pod.agentex"
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", original)
    monkeypatch.setattr(otel_metrics.os, "getpid", lambda: 42)
    otel_metrics._resource_with_unique_instance_id()
    assert os.environ["OTEL_RESOURCE_ATTRIBUTES"] == original


@pytest.mark.unit
def test_sync_instance_id_to_env_updates_env(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agentex")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "k8s.pod.name=operator-pod,service.instance.id=agentex.operator-pod.agentex",
    )
    monkeypatch.setattr(otel_metrics.os, "getpid", lambda: 6789)

    otel_metrics._sync_instance_id_to_env("agentex.operator-pod.agentex.6789")

    env = os.environ["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.instance.id=agentex.operator-pod.agentex.6789" in env
    assert "k8s.pod.name=operator-pod" in env


@pytest.mark.unit
def test_resource_with_unique_instance_id_from_otel_env(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agentex")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "k8s.pod.name=operator-pod,k8s.namespace.name=agentex,"
        "k8s.deployment.name=agentex,service.instance.id=agentex.operator-pod.agentex",
    )
    monkeypatch.setattr(otel_metrics.os, "getpid", lambda: 6789)

    resource = otel_metrics._resource_with_unique_instance_id()
    attrs = resource.attributes
    assert attrs.get("service.name") == "agentex"
    assert attrs.get("k8s.pod.name") == "operator-pod"
    assert attrs.get("service.instance.id") == "agentex.operator-pod.agentex.6789"


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
def test_init_after_shutdown_in_standalone_mode(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    first = otel_metrics.init_otel_metrics()
    assert first is not None
    assert otel_metrics._meter_provider is first

    otel_metrics.shutdown_otel_metrics()
    assert otel_metrics._initialized is False
    assert otel_metrics._meter_provider is None

    second = otel_metrics.init_otel_metrics()
    assert second is not None
    assert otel_metrics._initialized is True
    assert otel_metrics.get_meter("agentex.test") is not None


@pytest.mark.unit
def test_shutdown_does_not_replace_global_meter_provider(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = otel_metrics.init_otel_metrics()
    assert provider is not None
    global_before = metrics.get_meter_provider()

    with patch.object(metrics, "set_meter_provider") as set_provider:
        otel_metrics.shutdown_otel_metrics()

    set_provider.assert_not_called()
    assert metrics.get_meter_provider() is global_before


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
