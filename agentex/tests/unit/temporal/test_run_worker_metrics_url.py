import pytest
from src.temporal.run_worker import build_metrics_url


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
