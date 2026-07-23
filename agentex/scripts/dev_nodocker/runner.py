"""Orchestrate provisioning, migration, the API + worker, and clean teardown."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from scripts.dev_nodocker.config import (
    LOOPBACK,
    DevNoDockerConfig,
    build_env,
    resolve_config,
)
from scripts.dev_nodocker.services import (
    provision_mongo,
    provision_otel,
    provision_postgres,
    provision_redis,
    provision_temporal,
    teardown_redis,
)
from scripts.dev_nodocker.supervise import (
    run_migrations,
    spawn,
    terminate,
    wait_for_health,
)

logger = logging.getLogger(__name__)


async def run(cfg: DevNoDockerConfig) -> int:
    if cfg.ephemeral:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)

    pg_server = None
    redis_server = None
    temporal_env = None
    mongo_proc: asyncio.subprocess.Process | None = None
    otel_proc: asyncio.subprocess.Process | None = None
    procs: list[tuple[str, asyncio.subprocess.Process]] = []

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        pg_server, database_url = provision_postgres(cfg)
        redis_server, redis_url = provision_redis(cfg)

        # MongoDB is required for the full stack (the Temporal worker builds
        # Mongo-backed repositories at boot), so it is always provisioned.
        mongo_proc, mongo_uri = await provision_mongo(cfg)

        temporal_address: str | None = None
        if cfg.temporal:
            temporal_env, temporal_address = await provision_temporal(cfg)

        otel_endpoint: str | None = None
        if cfg.otel:
            otel_proc, otel_endpoint = await provision_otel(cfg)

        env = build_env(
            database_url=database_url,
            redis_url=redis_url,
            temporal_address=temporal_address,
            mongo_uri=mongo_uri,
            otel_endpoint=otel_endpoint,
        )

        await run_migrations(cfg, env)

        logger.info("Starting API server on http://localhost:%d", cfg.api_port)
        # Bind 0.0.0.0 (not LOOPBACK) so the containerized frontend / other hosts can reach it.
        api = await spawn(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(cfg.api_port),
                "--reload",
                "--reload-dir",
                "src",
            ],
            cwd=cfg.agentex_dir,
            env=env,
        )
        procs.append(("api", api))

        if cfg.temporal:
            worker = await spawn(
                "worker",
                [sys.executable, "src/temporal/run_worker.py"],
                cwd=cfg.agentex_dir,
                env=env,
            )
            procs.append(("worker", worker))

        if await wait_for_health(cfg.api_port):
            logger.info("API is up.")
        else:
            logger.warning(
                "API did not pass /healthz within the timeout; check the logs above."
            )

        _print_banner(cfg, mongo_uri, temporal_address, otel_endpoint)

        # Exit when a signal arrives or a core process dies unexpectedly.
        waiters = [asyncio.create_task(p.wait()) for _, p in procs]
        stop_task = asyncio.create_task(stop.wait())
        await asyncio.wait([stop_task, *waiters], return_when=asyncio.FIRST_COMPLETED)
        if not stop.is_set():
            dead = [name for name, p in procs if p.returncode is not None]
            logger.error(
                "A managed process exited unexpectedly: %s. Shutting down.",
                ", ".join(dead) or "?",
            )
            # Non-zero so callers ($?, make dev-no-docker, CI) detect the crash;
            # a signal-driven shutdown (stop set) is the clean path and returns 0.
            return 1
        return 0
    finally:
        # Tear down consumers (worker, api) first, then services in reverse.
        for name, proc in reversed(procs):
            await terminate(proc, name)
        if temporal_env is not None:
            logger.info("Stopping Temporal dev server ...")
            try:
                await temporal_env.shutdown()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Temporal shutdown raised %s", exc)
        if otel_proc is not None:
            await terminate(otel_proc, "otel")
        if mongo_proc is not None:
            await terminate(mongo_proc, "mongo")
        if redis_server is not None:
            logger.info("Stopping embedded Redis ...")
            teardown_redis(redis_server)
        if pg_server is not None:
            logger.info("Stopping embedded Postgres ...")
            try:
                pg_server.cleanup()
            except Exception as exc:  # noqa: BLE001
                logger.warning("pgserver cleanup raised %s", exc)
        logger.info("All local services stopped.")


def _print_banner(
    cfg: DevNoDockerConfig,
    mongo_uri: str | None,
    temporal_address: str | None,
    otel_endpoint: str | None,
) -> None:
    temporal = (
        f"{LOOPBACK}:{cfg.temporal_port} (UI http://localhost:{cfg.ui_port})"
        if temporal_address
        else "off"
    )
    print("\n" + "=" * 52, flush=True)
    print("  agentex backend (no Docker)", flush=True)
    print(f"  API:         http://localhost:{cfg.api_port}", flush=True)
    print(f"  Swagger:     http://localhost:{cfg.api_port}/swagger", flush=True)
    print("  Postgres:    embedded (socket)", flush=True)
    print(f"  Redis:       {LOOPBACK}:{cfg.redis_port}", flush=True)
    print(f"  Mongo:       {mongo_uri or 'off'}", flush=True)
    print(f"  Temporal:    {temporal}", flush=True)
    print(f"  OTel:        {otel_endpoint or 'off'}", flush=True)
    print("  Ctrl-C to stop everything.", flush=True)
    print("=" * 52 + "\n", flush=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = resolve_config()
    try:
        code = asyncio.run(run(cfg))
    except RuntimeError as exc:
        # Fail-fast provisioning errors (e.g. Mongo required but missing) read as a
        # single actionable line, not a traceback.
        logger.error("%s", exc)
        raise SystemExit(1) from None
    raise SystemExit(code)
