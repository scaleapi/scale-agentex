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
@pytest.mark.parametrize("environment", ["development", "production"])
def test_absent_adapter_preserves_default_logging(
    tmp_path, monkeypatch, adapter, environment
):
    monkeypatch.setenv("ENVIRONMENT", environment)
    result = run_python(
        """
        import importlib, io, logging, sys
        from src.utils import observability
        assert not observability.uses_observability_adapter()
        assert "fastapi" not in sys.modules
        assert "opentelemetry" not in sys.modules
        from src.utils import logging as agentex_logging
        external_output = io.StringIO()
        external_handler = logging.StreamHandler(external_output)
        external_formatter = logging.Formatter("external: %(message)s")
        external_handler.setFormatter(external_formatter)
        logger = logging.getLogger("test.default")
        logger.addHandler(external_handler)
        logging.getLogger().addHandler(logging.NullHandler())
        assert agentex_logging.make_logger("test.default") is logger
        original_handlers = list(logger.handlers)
        assert agentex_logging.make_logger("test.default") is logger
        importlib.reload(agentex_logging)
        assert agentex_logging.make_logger("test.default") is logger
        logger.info("one-output-only token=%s", "sensitive-value")
        assert len(logger.handlers) == 2
        assert logger.handlers == original_handlers
        assert external_handler.formatter is external_formatter
        assert external_output.getvalue() == "external: one-output-only token=[REDACTED]\\n"
        """,
        tmp_path,
        adapter=adapter,
    )
    assert result.returncode == 0, result.stderr
    assert (result.stdout + result.stderr).count("one-output-only") == 1
    assert "sensitive-value" not in result.stdout + result.stderr
    if environment == "production":
        assert json.loads(result.stderr)["message"] == (
            "one-output-only token=[REDACTED]"
        )


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
        "from src.utils.observability import uses_observability_adapter; uses_observability_adapter()",
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


@pytest.mark.parametrize("adapter", [None, "missing_test_adapter.worker"])
def test_worker_callbacks_preserve_absent_adapter_behavior(tmp_path, adapter):
    result = run_python(
        """
        from src.utils import observability
        observability.initialize_worker()
        assert not observability.uses_observability_adapter()
        assert observability.temporal_client_interceptors() == ()
        assert observability.get_meter('test', '1.0') is None
        observability.shutdown()
        """,
        tmp_path,
        adapter=adapter,
    )
    assert result.returncode == 0, result.stderr


def test_worker_initializes_once_before_dependency_imports(tmp_path):
    (tmp_path / "worker_adapter.py").write_text(
        textwrap.dedent("""
        import sys
        calls = []
        def initialize_worker():
            assert 'src.config.dependencies' not in sys.modules
            assert 'src.adapters.temporal.client_factory' not in sys.modules
            assert 'src.utils.database' not in sys.modules
            calls.append('initialize-worker')
        def shutdown():
            calls.append('shutdown')
    """)
    )
    result = run_python(
        """
        import asyncio, runpy
        from unittest.mock import patch
        with patch.object(asyncio, 'run', lambda coroutine: coroutine.close()):
            runpy.run_module('src.temporal.run_worker', run_name='__main__')
        from src.utils import observability
        import worker_adapter
        observability.initialize_worker()
        assert observability.temporal_client_interceptors() == ()
        assert observability.get_meter('test', '1.0') is None
        from temporalio import workflow
        from src.temporal.workflows import healthcheck_workflow, retention_cleanup_workflow
        assert healthcheck_workflow.logger is workflow.logger
        assert retention_cleanup_workflow.logger is workflow.logger
        observability.shutdown()
        observability.shutdown()
        assert worker_adapter.calls == ['initialize-worker', 'shutdown']
        """,
        tmp_path,
        adapter="worker_adapter",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_failed_worker_initialization_cleans_up(tmp_path):
    (tmp_path / "failing_worker_adapter.py").write_text(
        textwrap.dedent("""
        def initialize_worker():
            raise RuntimeError('partial worker setup')
        def shutdown():
            print('worker-cleanup')
    """)
    )
    result = run_python(
        "import runpy; runpy.run_module('src.temporal.run_worker', run_name='__main__')",
        tmp_path,
        adapter="failing_worker_adapter",
    )
    assert result.returncode != 0
    assert "partial worker setup" in result.stderr
    assert result.stdout.count("worker-cleanup") == 1


def test_api_schedule_queue_lookup_does_not_bootstrap_worker(tmp_path):
    (tmp_path / "api_only_adapter.py").write_text(
        "def initialize(app): pass\n"
        "def shutdown(): raise AssertionError('API adapter was shut down')\n"
    )
    result = run_python(
        """
        from src.domain.services.agent_run_schedule_service import AgentRunScheduleService
        from src.utils import observability
        assert AgentRunScheduleService._task_queue(None) == 'agentex-server'
        assert not observability._worker_initialized
        assert not observability._shutdown_called
        """,
        tmp_path,
        adapter="api_only_adapter",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_adapter_meter_keeps_application_metrics_on_shared_provider(tmp_path):
    (tmp_path / "shared_meter_adapter.py").write_text(
        textwrap.dedent("""
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        def get_meter(name, version):
            return provider.get_meter(name, version)
        def shutdown():
            provider.shutdown()
    """)
    )
    result = run_python(
        """
        from opentelemetry import metrics
        from src.utils.cache_metrics import record_cache_access
        from src.utils import otel_metrics, observability
        import shared_meter_adapter
        before = metrics.get_meter_provider()
        record_cache_access('worker', 'hit')
        assert otel_metrics.init_otel_metrics() is None
        assert metrics.get_meter_provider() is before
        data = shared_meter_adapter.reader.get_metrics_data()
        points = [
            (metric.name, scope.scope.name, dict(point.attributes))
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            for point in metric.data.data_points
        ]
        assert ('auth_cache.access', 'agentex.auth_cache', {'cache': 'worker', 'result': 'hit'}) in points
        observability.shutdown()
        """,
        tmp_path,
        adapter="shared_meter_adapter",
    )
    assert result.returncode == 0, result.stdout + result.stderr
