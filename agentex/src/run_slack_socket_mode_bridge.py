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

import httpx
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config.dependencies import database_async_read_write_session_maker
from src.config.environment_variables import EnvironmentVariables
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.services.slack_socket_mode_bridge import SlackSocketModeBridge
from src.utils import credential_encryption
from src.utils.database import async_db_engine_creator
from src.utils.logging import make_logger
from src.utils.otel_metrics import shutdown_otel_metrics

logger = make_logger(__name__)

PROBE_PORT = 5004
# The bridge reads triggers once a minute and one agent per forwarded event.
DB_POOL_SIZE = 2
DB_MAX_OVERFLOW = 3
DB_POOL_RECYCLE_SECONDS = 3600


def create_engine(database_url: str) -> AsyncEngine:
    """The bridge's only database connection: a small pool for trigger and agent reads.

    The bridge does not load the API's global dependencies (Temporal, MongoDB,
    Redis, Kubernetes config); it needs none of them, and waiting on them would
    delay the probe server.
    """
    return create_async_engine(
        "postgresql+asyncpg://",
        async_creator=async_db_engine_creator(database_url),
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=DB_POOL_RECYCLE_SECONDS,
    )


def create_slack_socket_mode_bridge(
    engine: AsyncEngine, http_client: httpx.AsyncClient
) -> SlackSocketModeBridge:
    """Build the bridge on one database engine and HTTP client.

    The bridge only reads triggers and agents, so every session uses ``engine``.
    """
    session_maker = database_async_read_write_session_maker(engine)
    return SlackSocketModeBridge(
        agent_api_key_repository=AgentAPIKeyRepository(session_maker, session_maker),
        agent_repository=AgentRepository(session_maker, session_maker),
        http_client=http_client,
    )


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

        # App tokens are stored encrypted, so without the key no trigger can be
        # served; refuse once here rather than failing per trigger.
        if not credential_encryption.is_configured():
            logger.error(
                "%s is not configured, so stored Slack app tokens cannot be read; "
                "the Slack Socket Mode bridge will not start.",
                credential_encryption.ENV_KEY,
            )
            raise SystemExit(1)

        engine = create_engine(EnvironmentVariables.refresh().DATABASE_URL)
        cleanup.push_async_callback(engine.dispose)
        http_client = httpx.AsyncClient()
        cleanup.push_async_callback(http_client.aclose)
        bridge = create_slack_socket_mode_bridge(engine, http_client)

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
