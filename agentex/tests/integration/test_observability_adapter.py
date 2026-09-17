"""Exercise the public adapter in spawned Uvicorn workers over real HTTP."""

import json
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


def test_spawned_workers_configure_and_clean_up_independently(tmp_path):
    (tmp_path / "probe_adapter.py").write_text(
        textwrap.dedent("""
        import json
        import logging
        import os
        import sys
        from pathlib import Path

        def record(stage):
            path = Path(os.environ["PROBE_EVENTS"]) / (str(os.getpid()) + ".jsonl")
            with path.open("a") as output:
                output.write(json.dumps({"stage": stage, "pid": os.getpid(),
                    "resource": os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")}) + "\\n")

        def initialize_logging():
            assert "src.utils.logging" not in sys.modules
            logging.basicConfig(stream=sys.stdout, level=logging.INFO)
            record("logging")
            return True

        def configure_app(app):
            from fastapi import Request
            from src.api.logged_api_route import LoggedAPIRoute
            from src.utils.logging import ctx_var_request_id
            assert any(route.path == "/agents" for route in app.routes)
            record("configured")
            async def probe(request: Request):
                return {"pid": os.getpid(), "request_id": ctx_var_request_id.get(),
                        "body": await request.json()}
            app.router.add_api_route("/api/observability-probe", probe, methods=["POST"],
                                     route_class_override=LoggedAPIRoute)

        def shutdown():
            record("shutdown")
    """)
    )
    (tmp_path / "probe_server.py").write_text(
        textwrap.dedent("""
        from types import SimpleNamespace
        import src.api.app as api
        async def noop():
            pass
        api.dependencies.startup_global_dependencies = noop
        api.dependencies.async_shutdown = noop
        api.dependencies.shutdown = lambda: None
        api.GlobalDependencies = lambda: SimpleNamespace(postgres_metrics_collector=None)
        api.configure_statsd = lambda: None
        app = api.app
    """)
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OTEL_", "AGENTEX_OBSERVABILITY_", "DD_"))
    }
    env.update(
        PYTHONPATH=f"{tmp_path}{os.pathsep}{BACKEND}",
        AGENTEX_OBSERVABILITY_MODULE="probe_adapter",
        PROBE_EVENTS=str(tmp_path),
        OTEL_RESOURCE_ATTRIBUTES="service.instance.id=api.pod",
        CI="true",
        DD_TRACE_ENABLED="false",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log_path = tmp_path / "server.log"
    with log_path.open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "probe_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                "2",
                "--log-level",
                "warning",
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(log_path.read_text())
                records = [
                    json.loads(line)
                    for path in tmp_path.glob("*.jsonl")
                    for line in path.read_text().splitlines()
                ]
                if sum(record["stage"] == "configured" for record in records) == 2:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Workers did not start: " + log_path.read_text())

            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        health = client.get("/healthz")
                        break
                    except httpx.ConnectError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
                assert health.status_code == 200
                body = {"prompt": "private-payload-marker"}
                response = client.post(
                    "/api/observability-probe",
                    json=body,
                    headers={"x-request-id": "ingress-123"},
                )
                assert response.status_code == 200, response.text
                assert response.headers["x-request-id"] == "ingress-123"
                assert response.json()["request_id"] == "ingress-123"
                assert response.json()["body"] == body
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    event_files = list(tmp_path.glob("*.jsonl"))
    assert len(event_files) == 2, log_path.read_text()
    for path in event_files:
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert [record["stage"] for record in records] == [
            "logging",
            "configured",
            "shutdown",
        ]
        configured = records[1]
        assert (
            f"service.instance.id=api.pod.{configured['pid']}" in configured["resource"]
        )
    logs = log_path.read_text()
    assert "private-payload-marker" not in logs
    assert logs.count("Request received") == 1
    assert logs.count("Response sent") == 1
