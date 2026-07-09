"""Pure config/env for the docker-free local runner — no side effects, unit-testable."""

from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# scripts/dev_local/config.py -> agentex is three parents up; the runner launches
# uvicorn/alembic/the worker from there.
AGENTEX_DIR = Path(__file__).resolve().parents[2]

# Loopback address every local service binds to and is dialed on. A constant, not an
# env var: a dev runner should always bind loopback. (The API server binds 0.0.0.0 on
# purpose — see runner.run; banner URLs say "localhost" for readability.)
LOOPBACK = "127.0.0.1"


@dataclass
class DevLocalConfig:
    agentex_dir: Path
    data_dir: Path
    ephemeral: bool
    api_port: int
    redis_port: int
    temporal: bool
    temporal_port: int
    ui_port: int
    mongo_uri: str | None  # external override; when None, launch a local mongod
    mongo_port: int
    otel: bool
    otel_port: int

    @property
    def pg_data(self) -> Path:
        return self.data_dir / "pgdata"

    @property
    def redis_dir(self) -> Path:
        return self.data_dir / "redis"

    @property
    def temporal_db(self) -> Path:
        return self.data_dir / "temporal.sqlite"

    @property
    def mongo_data(self) -> Path:
        return self.data_dir / "mongo"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dev_local",
        description="Run the full agentex backend locally without Docker.",
    )
    # Everything is on by default; --no-<svc> opts out.
    p.add_argument(
        "--temporal",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Start the Temporal dev server (+ UI) and the agentex worker (default: on).",
    )
    p.add_argument(
        "--otel",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Start the OpenTelemetry collector (default: on; optional — skipped with a warning if not installed).",
    )
    # --lean and --full are opposite shortcuts and cannot be combined.
    stack_group = p.add_mutually_exclusive_group()
    stack_group.add_argument(
        "--lean",
        action="store_true",
        help="Only Postgres + Redis + API + MongoDB (turns off temporal and otel). MongoDB is always started — the stack requires it.",
    )
    stack_group.add_argument(
        "--full",
        action="store_true",
        help="Run the whole stack (pg + redis + api + temporal + mongo + otel). This is already the default; the flag exists so `--full` is accepted rather than rejected.",
    )
    p.add_argument(
        "--mongo-uri",
        default=None,
        help="Use an EXTERNAL MongoDB at this URI instead of launching a local mongod.",
    )
    p.add_argument(
        "--port", type=int, default=5003, help="Port for the API server (default 5003)."
    )
    p.add_argument(
        "--redis-port",
        type=int,
        default=6390,
        help="TCP port for embedded Redis (default 6390; avoids a Docker Redis on 6379).",
    )
    p.add_argument(
        "--temporal-port",
        type=int,
        default=7233,
        help="Port for the Temporal frontend (default 7233).",
    )
    p.add_argument(
        "--ui-port",
        type=int,
        default=8233,
        help="Port for the Temporal Web UI (default 8233).",
    )
    p.add_argument(
        "--mongo-port",
        type=int,
        default=27017,
        help="Port for the local mongod (default 27017).",
    )
    p.add_argument(
        "--otel-port",
        type=int,
        default=4317,
        help="OTLP gRPC port for the collector (default 4317).",
    )
    p.add_argument(
        "--data-dir",
        default=None,
        help="Directory for persistent datastore data (default <agentex>/.dev-local). Ignored with --ephemeral.",
    )
    p.add_argument(
        "--ephemeral",
        action="store_true",
        help="Use a throwaway temp data dir wiped on exit (fresh state every run).",
    )
    return p


def resolve_config(
    argv: list[str] | None = None, *, agentex_dir: Path = AGENTEX_DIR
) -> DevLocalConfig:
    """Parse argv into a DevLocalConfig. Pure: no filesystem side effects."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.ephemeral:
        # Per-process-unique so a hard-killed run can't leave a pgserver orphan that the
        # next --ephemeral run re-attaches to (which would defeat "fresh state every run").
        data_dir = Path(tempfile.gettempdir()) / f"agentex-dev-local-{os.getpid()}"
    elif args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
    else:
        data_dir = agentex_dir / ".dev-local"

    # --lean forces the optional services off; --full is a no-op (they're already on).
    # MongoDB is always started — the stack requires it — so --lean does not touch it.
    temporal = args.temporal and not args.lean
    otel = args.otel and not args.lean

    return DevLocalConfig(
        agentex_dir=agentex_dir,
        data_dir=data_dir,
        ephemeral=args.ephemeral,
        api_port=args.port,
        redis_port=args.redis_port,
        temporal=temporal,
        temporal_port=args.temporal_port,
        ui_port=args.ui_port,
        mongo_uri=args.mongo_uri,
        mongo_port=args.mongo_port,
        otel=otel,
        otel_port=args.otel_port,
    )


def build_env(
    *,
    database_url: str,
    redis_url: str,
    temporal_address: str | None,
    mongo_uri: str | None,
    otel_endpoint: str | None,
) -> dict[str, str]:
    """Build the environment for the API/worker subprocesses. Pure.

    An optional service's env var is set ONLY when that service was provisioned (and any
    inherited value is dropped), so the backend's feature gates see the true state and a
    leftover env can't re-enable a service we didn't start.
    """
    env = dict(os.environ)
    env["ENVIRONMENT"] = "development"
    env["DATABASE_URL"] = database_url
    env["REDIS_URL"] = redis_url
    env["MONGODB_DATABASE_NAME"] = "agentex"

    # Agents register their ACP URL at host.docker.internal (SDK default, for a Docker
    # backend); that name doesn't resolve for this host-process backend, so have it dial
    # such agents at loopback instead. Only the sentinel host is rewritten — see
    # src/utils/acp_url.py.
    env["AGENTEX_ACP_HOST_OVERRIDE"] = LOOPBACK

    if mongo_uri:
        env["MONGODB_URI"] = mongo_uri
    else:
        env.pop("MONGODB_URI", None)

    if temporal_address:
        env["TEMPORAL_ADDRESS"] = temporal_address
        env["AGENTEX_SERVER_TASK_QUEUE"] = "agentex-server"
    else:
        env.pop("TEMPORAL_ADDRESS", None)

    if otel_endpoint:
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = otel_endpoint
        env["OTEL_SERVICE_NAME"] = "agentex-api"
    else:
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    return env
