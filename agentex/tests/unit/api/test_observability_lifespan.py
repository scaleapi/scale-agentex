"""Adapter cleanup remains independent from dependency cleanup."""

import asyncio
import importlib
import threading
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("failure", [None, "startup", "http", "async", "sync"])
async def test_cleanup_runs_after_startup_or_dependency_failure(monkeypatch, failure):
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
    from src.utils import observability

    monkeypatch.setattr(observability, "shutdown", close_adapter)

    async def run():
        async with app_module.lifespan(app_module.fastapi_app):
            await asyncio.sleep(0)
            record("serve")

    if failure:
        with pytest.raises(RuntimeError, match=failure):
            await run()
    else:
        await run()
    assert calls[-5:] == ["http", "async", "sync", "metrics-close", "adapter"]
    assert ("serve" in calls) is (failure != "startup")
