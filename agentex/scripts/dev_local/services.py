"""Provision the backing datastores/services as host processes (side effects)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
from typing import Any
from urllib.parse import urlsplit

from scripts.dev_local.config import LOOPBACK, DevLocalConfig
from scripts.dev_local.supervise import spawn, terminate, wait_for_port

logger = logging.getLogger(__name__)


def provision_postgres(cfg: DevLocalConfig) -> tuple[Any, str]:
    """Start an embedded Postgres and ensure the 'agentex' database exists.

    The returned socket-form `postgresql://` URL works for both the async app (asyncpg)
    and alembic (psycopg2) — adjust_db_url normalizes the scheme for each.
    """
    import pgserver

    cfg.pg_data.parent.mkdir(
        parents=True, exist_ok=True
    )  # get_server makes pgdata itself
    logger.info("Provisioning embedded Postgres at %s ...", cfg.pg_data)
    server = pgserver.get_server(
        cfg.pg_data, cleanup_mode="delete" if cfg.ephemeral else "stop"
    )

    # psql() doesn't stop-on-error and CREATE DATABASE can't be IF NOT EXISTS, so guard.
    existing = server.psql("SELECT 1 FROM pg_database WHERE datname = 'agentex';")
    if "(1 row)" not in existing:
        server.psql("CREATE DATABASE agentex;")
        logger.info("Created database 'agentex'.")

    return server, server.get_uri(database="agentex")


def provision_redis(cfg: DevLocalConfig) -> tuple[Any, str]:
    """Start an embedded real redis-server on a TCP port. Returns (server, url)."""
    import redislite

    cfg.redis_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Provisioning embedded Redis on %s:%s ...", LOOPBACK, cfg.redis_port)
    # port MUST go inside serverconfig — a top-level port= kwarg switches redislite into
    # client-only mode and starts no server.
    server = redislite.Redis(
        str(cfg.redis_dir / "dump.rdb"),
        serverconfig={"port": str(cfg.redis_port), "bind": LOOPBACK},
    )
    port = server.config_get("port")["port"]
    return server, f"redis://{LOOPBACK}:{port}/0"


async def provision_temporal(cfg: DevLocalConfig) -> tuple[Any, str]:
    """Start the Temporal dev server (+ Web UI). Returns (env, address)."""
    from temporalio.testing import WorkflowEnvironment

    db_file: str | None = None
    if not cfg.ephemeral:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        db_file = str(cfg.temporal_db)

    logger.info(
        "Starting Temporal dev server on %s:%s (UI :%s) ...",
        LOOPBACK,
        cfg.temporal_port,
        cfg.ui_port,
    )
    env = await WorkflowEnvironment.start_local(
        ip=LOOPBACK,
        port=cfg.temporal_port,
        ui=True,
        ui_port=cfg.ui_port,
        dev_server_database_filename=db_file,
    )
    return env, f"{LOOPBACK}:{cfg.temporal_port}"


async def provision_mongo(
    cfg: DevLocalConfig,
) -> tuple[asyncio.subprocess.Process | None, str | None]:
    """Start a local mongod (or use an external URI). Returns (proc, uri).

    MongoDB is REQUIRED for the full stack (the Temporal worker builds Mongo-backed repos
    at boot), so this is always called and FAILS FAST if Mongo can't be made available —
    returning None would let the worker crash and take the stack down.
    """
    if cfg.mongo_uri:
        logger.info("Using external MongoDB at %s", cfg.mongo_uri)
        # Reachability check only for a plain single-host mongodb://host:port URI. SRV
        # (mongodb+srv://) and multi-host / replica-set URIs can't be TCP-probed naively.
        parsed = urlsplit(cfg.mongo_uri)
        try:
            host, port = parsed.hostname, parsed.port
        except ValueError:  # non-integer port in a multi-host netloc
            host, port = None, None
        probeable = (
            parsed.scheme == "mongodb"
            and host is not None
            and port is not None
            and "," not in (parsed.netloc or "")
        )
        if probeable and not await wait_for_port(None, host, port, timeout=5.0):
            raise RuntimeError(
                f"External MongoDB at {cfg.mongo_uri} is not reachable. Verify it is "
                f"running/accessible, or omit --mongo-uri to launch a local mongod."
            )
        return None, cfg.mongo_uri

    mongod = shutil.which("mongod")
    if not mongod:
        raise RuntimeError(
            "mongod not found on PATH, but MongoDB is required for the local stack. "
            "Install it (macOS: brew tap mongodb/brew && brew install mongodb-community; "
            "Linux: install the mongodb-org package so `mongod` is on PATH), or pass "
            "--mongo-uri to point at an external MongoDB."
        )

    cfg.mongo_data.mkdir(parents=True, exist_ok=True)
    logger.info("Provisioning MongoDB (mongod) on %s:%s ...", LOOPBACK, cfg.mongo_port)
    proc = await spawn(
        "mongo",
        [
            mongod,
            "--dbpath",
            str(cfg.mongo_data),
            "--port",
            str(cfg.mongo_port),
            "--bind_ip",
            LOOPBACK,
            "--quiet",
        ],
        cwd=cfg.agentex_dir,
        env=dict(os.environ),
    )
    if await wait_for_port(proc, LOOPBACK, cfg.mongo_port):
        return proc, f"mongodb://{LOOPBACK}:{cfg.mongo_port}"

    await terminate(proc, "mongo")
    raise RuntimeError(
        f"mongod failed to become ready on {LOOPBACK}:{cfg.mongo_port}. Check the port "
        f"is free and mongod can write to {cfg.mongo_data}, or pass --mongo-uri to point "
        f"at an external MongoDB."
    )


async def provision_otel(
    cfg: DevLocalConfig,
) -> tuple[asyncio.subprocess.Process | None, str | None]:
    """Start the OpenTelemetry collector if present. Returns (proc, otlp_endpoint).

    Optional: there's no bundled/pip collector, so we launch `otelcol-contrib`/`otelcol`
    when on PATH and otherwise continue without telemetry (the app is unaffected).
    """
    binary = shutil.which("otelcol-contrib") or shutil.which("otelcol")
    if not binary:
        logger.warning(
            "otel collector not found on PATH — skipping telemetry export (the app "
            "runs fine without it). To enable it, start via `./dev.sh local` (installs "
            "the otelcol-contrib release binary automatically) or install it yourself "
            "from https://github.com/open-telemetry/opentelemetry-collector-releases/releases."
        )
        return None, None

    config = cfg.agentex_dir / "otel" / "otel-collector-config.yaml"
    if not config.exists():
        logger.warning("otel config %s missing — skipping telemetry.", config)
        return None, None

    logger.info(
        "Provisioning OpenTelemetry collector on %s:%s ...", LOOPBACK, cfg.otel_port
    )
    proc = await spawn(
        "otel",
        [binary, "--config", str(config)],
        cwd=cfg.agentex_dir,
        env=dict(os.environ),
    )
    if await wait_for_port(proc, LOOPBACK, cfg.otel_port, timeout=15.0):
        return proc, f"http://{LOOPBACK}:{cfg.otel_port}"

    logger.warning(
        "otel collector did not become ready — continuing without telemetry."
    )
    await terminate(proc, "otel")
    return None, None


def teardown_redis(server: Any) -> None:
    import redis as redis_pkg

    pid = getattr(server, "pid", None)
    try:
        server.shutdown(
            save=False
        )  # NOT shutdown(now=True, force=True) — broken on this stack
    except redis_pkg.exceptions.ConnectionError:
        pass  # expected: server drops the socket while replying
    except Exception as exc:  # noqa: BLE001 - best-effort teardown
        logger.warning("redislite shutdown raised %s; falling back to signal", exc)
    # Daemonized server leaks on hard exit; make sure the pid is gone.
    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
