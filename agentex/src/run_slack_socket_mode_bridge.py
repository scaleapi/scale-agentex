"""Slack Socket Mode bridge entry point.

Runs the bridge as its own process so the number of Socket Mode connections per
Slack app equals the number of bridge replicas, independent of how many API pods
and uvicorn workers there are. Slack caps an app at 10 connections.

Serves ``/healthz`` (liveness) and ``/readyz`` (trigger list loaded) on
``PROBE_PORT``. On SIGTERM the sockets are closed, so Slack moves delivery to the
remaining replicas.
"""

# ruff: noqa: E402
# Instrument libraries before dependency modules bind their constructors.
from src.utils import observability

if __name__ == "__main__":
    observability.initialize_worker()

import asyncio
import signal
from contextlib import AsyncExitStack

from aiohttp import web

from src.adapters.http.adapter_httpx import HttpxGateway
from src.config import dependencies
from src.config.dependencies import startup_global_dependencies
from src.domain.services.slack_socket_mode_bridge import (
    SlackSocketModeBridge,
    create_slack_socket_mode_bridge,
)
from src.utils.logging import make_logger
from src.utils.otel_metrics import shutdown_otel_metrics

logger = make_logger(__name__)

PROBE_PORT = 5004


def build_probe_app(bridge: SlackSocketModeBridge) -> web.Application:
    async def healthz(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def readyz(_: web.Request) -> web.Response:
        if bridge.ready:
            return web.Response(text="ok")
        return web.Response(status=503, text="triggers not loaded")

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/readyz", readyz)
    return app


async def main(probe_port: int = PROBE_PORT) -> None:
    async with AsyncExitStack() as cleanup:
        if observability.uses_observability_adapter():
            cleanup.push_async_callback(asyncio.to_thread, observability.shutdown)
        else:
            cleanup.callback(shutdown_otel_metrics)
        cleanup.callback(dependencies.shutdown)
        cleanup.push_async_callback(dependencies.async_shutdown)
        cleanup.push_async_callback(HttpxGateway.close_clients)
        await startup_global_dependencies()

        bridge = create_slack_socket_mode_bridge()
        if bridge is None:
            raise SystemExit(1)

        runner = web.AppRunner(build_probe_app(bridge))
        await runner.setup()
        cleanup.push_async_callback(runner.cleanup)
        await web.TCPSite(runner, port=probe_port).start()

        # Last pushed, so on shutdown the sockets close before anything else.
        cleanup.push_async_callback(bridge.stop)
        await bridge.start()
        logger.info("Slack Socket Mode bridge started (probes on :%s)", probe_port)
        await asyncio.Event().wait()


async def _run_cli() -> None:
    """Run cleanup on SIGTERM as well as keyboard interruption."""
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(main())

    def request_shutdown() -> None:
        if not main_task.cancelling():
            main_task.cancel()

    loop.add_signal_handler(signal.SIGTERM, request_shutdown)
    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Received shutdown signal, Slack Socket Mode bridge stopped")
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


if __name__ == "__main__":
    asyncio.run(_run_cli())
