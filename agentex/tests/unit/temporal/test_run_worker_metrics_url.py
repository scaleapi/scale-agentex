import pytest
from scripts.dev_nodocker.config import build_env
from src.temporal import run_worker
from src.temporal.run_worker import build_metrics_url


@pytest.fixture(autouse=True)
def clear_metrics_environment(monkeypatch):
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL",
        "DD_AGENT_HOST",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_metrics_url_is_none_without_host():
    assert build_metrics_url(None) is None
    assert build_metrics_url("") is None
    assert build_metrics_url("   ") is None


@pytest.mark.unit
@pytest.mark.parametrize("host", ["localhost", "datadog-agent", "10.0.0.5"])
def test_hostname_and_ipv4_hosts_are_not_bracketed(host):
    assert build_metrics_url(host) == f"http://{host}:4317"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("::1", "http://[::1]:4317"),
        ("fe80::1", "http://[fe80::1]:4317"),
        ("[::1]", "http://[::1]:4317"),
        ("[::1]:", "http://[::1]:4317"),
    ],
)
def test_ipv6_literals_are_bracketed(host, expected):
    assert build_metrics_url(host) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("datadog-agent:5555", "http://datadog-agent:5555"),
        ("10.0.0.5:5555", "http://10.0.0.5:5555"),
        ("[::1]:5555", "http://[::1]:5555"),
    ],
)
def test_explicit_port_is_preserved(host, expected):
    assert build_metrics_url(host) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("http://collector:4318", "http://collector:4318/v1/metrics"),
        ("https://collector/prefix/", "https://collector/prefix/v1/metrics"),
        (" http://[::1]:4318/ ", "http://[::1]:4318/v1/metrics"),
    ],
)
def test_otel_base_endpoint_enables_http_without_dd_host(monkeypatch, base, expected):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", base)
    config = run_worker.build_metrics_config()
    assert config.url == expected
    assert config.http is True


@pytest.mark.unit
def test_metrics_endpoint_overrides_base_and_dd_host(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://unused:4318")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://collector/custom-metrics"
    )
    monkeypatch.setenv("DD_AGENT_HOST", "old-collector")
    config = run_worker.build_metrics_config()
    assert config.url == "http://collector/custom-metrics"
    assert config.http is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("general", "specific", "expected_url", "http"),
    [
        ("grpc", "", "http://collector:4317", False),
        ("grpc", "http/protobuf", "http://collector:4317/v1/metrics", True),
        ("http/protobuf", " GRPC ", "http://collector:4317", False),
        ("", "http", "http://collector:4317/v1/metrics", True),
        (" ", " ", "http://collector:4317/v1/metrics", True),
    ],
)
def test_otel_protocol_precedence(monkeypatch, general, specific, expected_url, http):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", general)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", specific)
    config = run_worker.build_metrics_config()
    assert config.url == expected_url
    assert config.http is http


@pytest.mark.unit
def test_blank_metrics_endpoint_uses_base(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", " ")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    assert run_worker.build_metrics_config().url == "http://collector:4318/v1/metrics"


@pytest.mark.unit
def test_dd_host_remains_grpc_fallback(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", " ")
    monkeypatch.setenv("DD_AGENT_HOST", "[::1]:5555")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    config = run_worker.build_metrics_config()
    assert config.url == "http://[::1]:5555"
    assert config.http is False


@pytest.mark.unit
def test_no_metrics_exporter_without_any_endpoint():
    assert run_worker.build_metrics_config() is None


@pytest.mark.unit
def test_local_runner_selects_grpc_for_its_collector(monkeypatch):
    env = build_env(
        database_url="postgresql://localhost/agentex",
        redis_url="redis://localhost:6379",
        mongo_uri=None,
        temporal_address="localhost:7233",
        otel_endpoint="http://localhost:4317",
    )
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    config = run_worker.build_metrics_config()
    assert config.url == "http://localhost:4317"
    assert config.http is False


@pytest.mark.unit
def test_unsupported_otel_protocol_is_rejected(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "http/json")
    with pytest.raises(ValueError, match="Unsupported Temporal metrics protocol"):
        run_worker.build_metrics_config()
