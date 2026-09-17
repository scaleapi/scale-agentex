"""Public adapter bootstrap runs before application imports."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
BACKEND = Path(__file__).resolve().parents[3]


def run_python(source, tmp_path, *, adapter=None, ci=False):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AGENTEX_OBSERVABILITY_", "OTEL_"))
    }
    env.update(PYTHONPATH=f"{tmp_path}{os.pathsep}{BACKEND}", CI=str(ci).lower())
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


def test_disabled_bootstrap_does_not_import_application_dependencies(tmp_path):
    result = run_python(
        """
        import sys
        from src.utils import observability
        observability.initialize_logging()
        assert not observability.is_logging_managed()
        assert "fastapi" not in sys.modules
        assert "src.utils.logging" not in sys.modules
        assert "opentelemetry" not in sys.modules
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_adapter_runs_before_loggers_and_after_routes(tmp_path):
    (tmp_path / "example_adapter.py").write_text(
        textwrap.dedent(
            """
            import logging
            import sys
            calls = []
            def initialize_logging():
                assert "src.utils.logging" not in sys.modules
                assert "src.utils.otel_metrics" not in sys.modules
                assert "fastapi" not in sys.modules
                calls.append("logging")
                logging.basicConfig(stream=sys.stdout, level=logging.INFO)
                return True
            def configure_app(app):
                assert any(route.path == "/agents" for route in app.routes)
                assert any(route.path.startswith("/tasks") for route in app.routes)
                assert len(app.user_middleware) >= 3
                calls.append("app")
            def shutdown():
                calls.append("shutdown")
            """
        )
    )
    result = run_python(
        """
        import json
        import sys
        from src.api.app import fastapi_app
        from src.utils import observability
        from src.utils.logging import make_logger
        import example_adapter
        observability.initialize_logging()
        observability.configure_app(fastapi_app)
        old_hook = sys.excepthook
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
    assert json.loads(result.stdout.splitlines()[-1]) == ["logging", "app", "shutdown"]


@pytest.mark.parametrize("ci", [False, True])
def test_missing_adapter_warns_or_fails_in_ci(tmp_path, ci):
    result = run_python(
        """
        from src.utils import observability
        observability.initialize_logging()
        assert not observability.is_logging_managed()
        """,
        tmp_path,
        adapter="missing_test_adapter",
        ci=ci,
    )
    assert (result.returncode != 0) is ci
    assert "observability" in result.stderr.lower()


def test_repeated_make_logger_adds_one_handler(tmp_path):
    result = run_python(
        """
        from src.utils.logging import make_logger
        logger = make_logger("test.default")
        make_logger("test.default")
        logger.info("one-output-only")
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert (result.stdout + result.stderr).count("one-output-only") == 1


@pytest.mark.parametrize("stage", ["logging", "app", "shutdown"])
@pytest.mark.parametrize("ci", [False, True])
def test_callback_failures_keep_default_startup_or_raise_in_ci(tmp_path, stage, ci):
    (tmp_path / "failing_adapter.py").write_text(
        textwrap.dedent(
            f"""
            def fail(stage):
                if stage == {stage!r}:
                    raise ValueError("adapter unavailable")
            def initialize_logging():
                fail("logging")
                return False
            def configure_app(app):
                fail("app")
            def shutdown():
                fail("shutdown")
            """
        )
    )
    result = run_python(
        """
        from src.utils import observability
        observability.initialize_logging()
        from fastapi import FastAPI
        observability.configure_app(FastAPI())
        observability.shutdown()
        assert not observability.is_logging_managed()
        """,
        tmp_path,
        adapter="failing_adapter",
        ci=ci,
    )
    assert (result.returncode != 0) is ci
    assert "adapter unavailable" in result.stderr


def test_failed_logging_skips_app_configuration_but_still_cleans_up(tmp_path):
    (tmp_path / "partial_adapter.py").write_text(
        textwrap.dedent(
            """
            def initialize_logging():
                raise RuntimeError("partial setup")
            def configure_app(app):
                raise AssertionError("must not configure after failed logging")
            def shutdown():
                print("partial-cleanup")
            """
        )
    )
    result = run_python(
        """
        from src.utils import observability
        observability.initialize_logging()
        from fastapi import FastAPI
        observability.configure_app(FastAPI())
        observability.shutdown()
        """,
        tmp_path,
        adapter="partial_adapter",
    )
    assert result.returncode == 0, result.stderr
    assert "must not configure" not in result.stderr
    assert "partial-cleanup" in result.stdout


def test_adapter_receives_native_metrics_provider_before_app_configuration(tmp_path):
    (tmp_path / "metrics_adapter.py").write_text(
        "def initialize_logging(): return False\n"
        "def configure_app(app):\n"
        "    from opentelemetry import metrics\n"
        "    from opentelemetry.sdk.metrics import MeterProvider\n"
        "    assert isinstance(metrics.get_meter_provider(), MeterProvider)\n"
        "def shutdown(): pass\n"
    )
    result = run_python(
        """
        import os
        os.environ['OTEL_EXPORTER_OTLP_METRICS_ENDPOINT'] = 'http://127.0.0.1:1/v1/metrics'
        os.environ['OTEL_EXPORTER_OTLP_METRICS_PROTOCOL'] = 'http/protobuf'
        from src.utils import observability
        observability.initialize_logging()
        class App: pass
        observability.configure_app(App())
        from src.utils.otel_metrics import shutdown_otel_metrics
        shutdown_otel_metrics()
        """,
        tmp_path,
        adapter="metrics_adapter",
        ci=True,
    )
    assert result.returncode == 0, result.stderr
