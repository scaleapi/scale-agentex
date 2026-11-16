"""Adapter cleanup remains independent from dependency cleanup."""

import asyncio
import importlib
import threading
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("failure", [None, "startup", "http", "async", "sync"])
async def test_cleanup_runs_after_startup_or_dependency_failure(
    monkeypatch, failure, managed
):
    app_module = importlib.import_module("src.api.app")
    calls = []
    loop_thread = threading.get_ident()

    def record(name):
        calls.append(name)
        if name == failure:
            raise RuntimeError(name)

    async def startup():
        record("startup")

    async def close_http():
        record("http")

    async def close_async():
        record("async")

    def close_adapter():
        assert threading.get_ident() != loop_thread
        record("adapter")

    monkeypatch.setattr(app_module, "init_otel_metrics", lambda: record("metrics-init"))
    monkeypatch.setattr(
        app_module, "shutdown_otel_metrics", lambda: record("metrics-close")
    )
    monkeypatch.setattr(app_module.dependencies, "startup_global_dependencies", startup)
    monkeypatch.setattr(app_module.dependencies, "async_shutdown", close_async)
    monkeypatch.setattr(app_module.dependencies, "shutdown", lambda: record("sync"))
    monkeypatch.setattr(app_module.HttpxGateway, "close_clients", close_http)
    monkeypatch.setattr(app_module, "configure_statsd", lambda: None)
    monkeypatch.setattr(
        app_module,
        "GlobalDependencies",
        lambda: SimpleNamespace(postgres_metrics_collector=None),
    )
    from src.domain.services.slack_socket_mode_bridge import SlackSocketModeBridge
    from src.utils import observability

    async def start_bridge(self):
        record("slack-socket-mode")

    # Sockets belong to the dedicated bridge process; per-API-worker sockets
    # would exceed Slack's 10-connection cap per app.
    monkeypatch.setattr(SlackSocketModeBridge, "start", start_bridge)
    monkeypatch.setattr(observability, "shutdown", close_adapter)
    monkeypatch.setattr(observability, "uses_observability_adapter", lambda: managed)

    async def run():
        async with app_module.lifespan(app_module.fastapi_app):
            await asyncio.sleep(0)
            record("serve")

    if failure:
        with pytest.raises(RuntimeError, match=failure):
            await run()
    else:
        await run()
    expected = ["http", "async", "sync", "adapter" if managed else "metrics-close"]
    assert calls[-4:] == expected
    assert ("metrics-init" in calls) is not managed
    assert ("serve" in calls) is (failure != "startup")
    assert "slack-socket-mode" not in calls
