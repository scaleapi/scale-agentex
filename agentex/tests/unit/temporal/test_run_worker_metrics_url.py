import pytest
from src.temporal.run_worker import build_metrics_url


@pytest.mark.unit
def test_metrics_url_is_none_when_host_unset():
    assert build_metrics_url(None) is None
    assert build_metrics_url("") is None


@pytest.mark.unit
@pytest.mark.parametrize("host", ["localhost", "datadog-agent", "10.0.0.5"])
def test_hostname_and_ipv4_are_not_bracketed(host):
    assert build_metrics_url(host) == f"http://{host}:4317"


@pytest.mark.unit
@pytest.mark.parametrize(
    "host,expected",
    [("::1", "http://[::1]:4317"), ("fe80::1", "http://[fe80::1]:4317")],
)
def test_ipv6_literal_is_bracketed(host, expected):
    assert build_metrics_url(host) == expected
