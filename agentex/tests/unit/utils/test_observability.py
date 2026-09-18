"""Select one telemetry owner before application imports."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
BACKEND = Path(__file__).resolve().parents[3]


def run_python(source, tmp_path, *, adapter=None):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AGENTEX_OBSERVABILITY_", "OTEL_", "DD_"))
    }
    env.update(PYTHONPATH=f"{tmp_path}{os.pathsep}{BACKEND}", DD_TRACE_ENABLED="false")
    if adapter:
        env["AGENTEX_OBSERVABILITY_MODULE"] = adapter
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("adapter", [None, "missing_test_adapter.api"])
def test_absent_adapter_preserves_default_logging(tmp_path, adapter):
    result = run_python(
        """
        import sys
        from src.utils import observability
        assert not observability.is_managed()
        assert "fastapi" not in sys.modules
        assert "opentelemetry" not in sys.modules
        from src.utils.logging import make_logger
        logger = make_logger("test.default")
        logger.info("one-output-only")
        assert len(logger.handlers) == 1
        """,
        tmp_path,
        adapter=adapter,
    )
    assert result.returncode == 0, result.stderr
    assert (result.stdout + result.stderr).count("one-output-only") == 1


def test_adapter_initializes_once_after_routes_without_import_time_handlers(tmp_path):
    (tmp_path / "example_adapter.py").write_text(
        textwrap.dedent("""
        import logging
        import sys
        calls = []
        def initialize(app):
            assert any(route.path == "/agents" for route in app.routes)
            assert any(route.path.startswith("/tasks") for route in app.routes)
            assert len(app.user_middleware) >= 3
            assert not logging.getLogger("src.api.app").handlers
            calls.append("initialize")
            logging.basicConfig(stream=sys.stdout, level=logging.INFO)
        def shutdown():
            calls.append("shutdown")
    """)
    )
    result = run_python(
        """
        import json, sys
        from src.utils import observability
        from src.api.app import fastapi_app
        old_hook = sys.excepthook
        from src.utils.logging import make_logger
        import example_adapter
        observability.initialize(fastapi_app)
        logger = make_logger("test.managed")
        logger.info("token=%s", "sensitive-value")
        assert not logger.handlers
        assert logger.propagate
        assert sys.excepthook is old_hook
        observability.shutdown()
        observability.shutdown()
        print(json.dumps(example_adapter.calls))
        """,
        tmp_path,
        adapter="example_adapter",
    )
    assert result.returncode == 0, result.stderr
    assert "sensitive-value" not in result.stdout + result.stderr
    assert result.stdout.count("[REDACTED]") == 1
    assert json.loads(result.stdout.splitlines()[-1]) == ["initialize", "shutdown"]


def test_broken_adapter_dependency_is_not_treated_as_absent(tmp_path):
    (tmp_path / "broken_adapter.py").write_text("import missing_adapter_dependency\n")
    result = run_python(
        "from src.utils.observability import is_managed; is_managed()",
        tmp_path,
        adapter="broken_adapter",
    )
    assert result.returncode != 0
    assert "missing_adapter_dependency" in result.stderr


def test_initialization_failure_cleans_up_without_starting_native_telemetry(tmp_path):
    (tmp_path / "failing_adapter.py").write_text(
        textwrap.dedent("""
        def initialize(app):
            raise RuntimeError("partial adapter setup")
        def shutdown():
            print("partial-cleanup")
    """)
    )
    result = run_python(
        "from src.api.app import app",
        tmp_path,
        adapter="failing_adapter",
    )
    assert result.returncode != 0
    assert "partial adapter setup" in result.stderr
    assert result.stdout.count("partial-cleanup") == 1


def test_managed_mode_disables_lazy_native_metrics_and_statsd(tmp_path):
    (tmp_path / "metrics_adapter.py").write_text(
        "def initialize(app): pass\ndef shutdown(): pass\n"
    )
    result = run_python(
        """
        import asyncio, os, socket
        os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://127.0.0.1:1'
        os.environ['DD_AGENT_HOST'] = '127.0.0.1'
        from datadog import initialize
        from opentelemetry import metrics
        from src.utils.otel_metrics import bootstrap_auto_instrumentation, init_otel_metrics, get_meter
        before = metrics.get_meter_provider()
        bootstrap_auto_instrumentation()
        assert init_otel_metrics() is None
        assert get_meter('native-probe') is None
        assert metrics.get_meter_provider() is before
        from src.utils.cache_metrics import record_cache_access
        from src.utils.schedule_metrics import record_schedule_temporal_op
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(('127.0.0.1', 0))
            receiver.settimeout(0.1)
            initialize(statsd_host='127.0.0.1', statsd_port=receiver.getsockname()[1])
            record_cache_access('probe', 'hit')
            record_schedule_temporal_op('create', 'success')
            try:
                data = receiver.recv(1024)
            except TimeoutError:
                data = b''
            assert not data, data
        from src.adapters.streams.adapter_redis import RedisStreamRepository
        class Redis:
            async def info(self):
                raise AssertionError('native Redis collection must be skipped')
        from types import SimpleNamespace
        probe = SimpleNamespace(redis=Redis(), _last_metrics_time=0)
        asyncio.run(RedisStreamRepository.send_redis_connection_metrics(probe))
        """,
        tmp_path,
        adapter="metrics_adapter",
    )
    assert result.returncode == 0, result.stdout + result.stderr
