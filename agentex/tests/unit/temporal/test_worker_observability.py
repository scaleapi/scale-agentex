"""Worker lifecycle and client instrumentation use one telemetry owner."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from src.adapters.temporal import client_factory
from src.temporal import run_worker
from src.utils import observability
from temporalio.runtime import OpenTelemetryConfig

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("managed", [False, True])
@pytest.mark.parametrize("metrics_url", [None, "http://collector:4317"])
@pytest.mark.parametrize("explicit_config", [False, True])
async def test_client_factory_adds_interceptors_without_changing_core_metrics(
    monkeypatch, managed, metrics_url, explicit_config
):
    interceptor = object()
    adapter = SimpleNamespace(temporal_client_interceptors=lambda: [interceptor])
    monkeypatch.setattr(observability, "_adapter", lambda: adapter if managed else None)
    connect = AsyncMock()
    monkeypatch.setattr(client_factory.Client, "connect", connect)
    runtime = Mock()
    monkeypatch.setattr(client_factory, "Runtime", runtime)
    config = (
        OpenTelemetryConfig(url="http://collector:4318/v1/metrics", http=True)
        if explicit_config
        else None
    )

    await client_factory.TemporalClientFactory.create_client(
        "localhost:7233",
        temporal_namespace="worker-tests",
        metrics_url=metrics_url,
        metrics_config=config,
    )

    options = connect.call_args.kwargs
    assert options["target_host"] == "localhost:7233"
    assert options["namespace"] == "worker-tests"
    assert options["data_converter"] is client_factory.custom_data_converter
    if managed:
        assert options["interceptors"] == [interceptor]
    else:
        assert "interceptors" not in options
    if config is not None or metrics_url:
        assert options["runtime"] is runtime.return_value
        core = runtime.call_args.kwargs["telemetry"].metrics
        assert core.url == (config.url if config is not None else metrics_url)
        assert core.metric_periodicity is None
        assert core.http is explicit_config
    else:
        runtime.assert_not_called()
        assert "runtime" not in options


@pytest.mark.parametrize(
    "failure", [None, "startup", "worker", "http", "async", "sync"]
)
@pytest.mark.parametrize("managed", [False, True])
async def test_main_cleanup_follows_worker_and_dependencies(
    monkeypatch, failure, managed
):
    calls = []
    loop_thread = threading.get_ident()

    def record(name):
        calls.append(name)
        if name == failure:
            raise RuntimeError(name)

    async def startup():
        record("startup")

    async def worker():
        try:
            record("worker")
        finally:
            record("worker-stopped")

    async def close_http():
        record("http")

    async def close_dependencies():
        record("async")

    def close_adapter():
        assert threading.get_ident() != loop_thread
        record("adapter")

    monkeypatch.setattr(run_worker, "startup_global_dependencies", startup)
    monkeypatch.setattr(run_worker, "GlobalDependencies", Mock())
    for name in (
        "database_async_read_write_engine",
        "database_async_read_write_session_maker",
        "database_async_read_only_session_maker",
        "AgentRepository",
        "httpx_client",
    ):
        monkeypatch.setattr(run_worker, name, Mock())
    monkeypatch.setattr(
        run_worker,
        "create_agentex_server_worker",
        lambda **kwargs: asyncio.create_task(worker()),
    )
    monkeypatch.setattr(run_worker.HttpxGateway, "close_clients", close_http)
    monkeypatch.setattr(run_worker.dependencies, "async_shutdown", close_dependencies)
    monkeypatch.setattr(run_worker.dependencies, "shutdown", lambda: record("sync"))
    monkeypatch.setattr(observability, "uses_observability_adapter", lambda: managed)
    monkeypatch.setattr(observability, "shutdown", close_adapter)
    monkeypatch.setattr(run_worker, "shutdown_otel_metrics", lambda: record("native"))

    if failure:
        with pytest.raises(RuntimeError, match=failure):
            await run_worker.main()
    else:
        await run_worker.main()

    assert calls[-4:] == ["http", "async", "sync", "adapter" if managed else "native"]
    if failure != "startup":
        assert calls.index("worker-stopped") < calls.index("http")


async def test_worker_inherits_client_interceptors_without_registering_twice(
    monkeypatch,
):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    monkeypatch.delenv("DD_AGENT_HOST", raising=False)
    client = object()
    worker = SimpleNamespace(run=AsyncMock(), shutdown=AsyncMock(), is_shutdown=False)
    worker_constructor = Mock(return_value=worker)
    monkeypatch.setattr(run_worker, "Worker", worker_constructor)
    monkeypatch.setattr(run_worker, "startup_global_dependencies", AsyncMock())
    monkeypatch.setattr(
        run_worker.EnvironmentVariables,
        "refresh",
        lambda: SimpleNamespace(TEMPORAL_ADDRESS="localhost:7233"),
    )
    monkeypatch.setattr(
        run_worker.TemporalClientFactory, "is_temporal_configured", lambda _: True
    )
    create_client = AsyncMock(return_value=client)
    monkeypatch.setattr(
        run_worker.TemporalClientFactory,
        "create_client_from_env",
        create_client,
    )

    await run_worker.run_worker()

    core = create_client.call_args.kwargs["metrics_config"]
    assert core.url == "http://collector:4318/v1/metrics"
    assert core.http is True
    assert worker_constructor.call_args.args == (client,)
    assert "interceptors" not in worker_constructor.call_args.kwargs
    worker.run.assert_awaited_once()
    worker.shutdown.assert_awaited_once()


async def test_cancellation_waits_for_worker_shutdown(monkeypatch):
    started = asyncio.Event()
    stopped = asyncio.Event()
    calls = []

    async def work():
        started.set()
        await stopped.wait()
        calls.append("worker-stopped")

    async def stop():
        calls.append("shutdown")
        stopped.set()

    worker = SimpleNamespace(run=work, shutdown=stop, is_shutdown=False)
    monkeypatch.setattr(run_worker, "Worker", Mock(return_value=worker))
    monkeypatch.setattr(run_worker, "startup_global_dependencies", AsyncMock())
    monkeypatch.setattr(
        run_worker.EnvironmentVariables,
        "refresh",
        lambda: SimpleNamespace(TEMPORAL_ADDRESS="localhost:7233"),
    )
    monkeypatch.setattr(
        run_worker.TemporalClientFactory, "is_temporal_configured", lambda _: True
    )
    monkeypatch.setattr(
        run_worker.TemporalClientFactory, "create_client_from_env", AsyncMock()
    )
    task = asyncio.create_task(run_worker.run_worker())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["shutdown", "worker-stopped"]


async def test_cli_signal_requests_cleanup_only_once(monkeypatch):
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_done = asyncio.Event()
    calls = []
    signal_callbacks = []
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "add_signal_handler",
        lambda _, callback: signal_callbacks.append(callback),
    )
    remove_signal_handler = Mock()
    monkeypatch.setattr(loop, "remove_signal_handler", remove_signal_handler)

    async def main():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await cleanup_done.wait()
            calls.append("cleanup-done")

    monkeypatch.setattr(run_worker, "main", main)
    task = asyncio.create_task(run_worker._run_cli())
    await started.wait()
    signal_callbacks[0]()
    await cleanup_started.wait()
    signal_callbacks[0]()
    cleanup_done.set()
    await task
    assert calls == ["cleanup-done"]
    remove_signal_handler.assert_called_once_with(run_worker.signal.SIGTERM)
