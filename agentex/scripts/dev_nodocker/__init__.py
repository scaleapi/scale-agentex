"""Run the agentex backend locally as host processes, with no Docker.

The engine behind `./dev.sh no-docker` / `make dev-no-docker`: it provisions embedded datastores,
runs migrations, and supervises uvicorn (plus a Temporal worker), tearing everything down
on Ctrl-C / SIGTERM. Postgres/Redis/Temporal need no system install (bundled /
auto-downloaded). MongoDB is REQUIRED for the full stack — the Temporal worker builds
Mongo-backed repositories at boot, so a missing/unreachable mongod fails fast instead of
crashing the worker. It is always started; --mongo-uri points at an external MongoDB
instead of launching a local mongod. The OTel collector is optional; --lean turns off
temporal/otel (but keeps MongoDB).

Modules: `config` (pure, unit-testable), `services` (provisioning), `supervise`
(subprocess plumbing), `runner` (orchestration).
"""

from scripts.dev_nodocker.config import (
    LOOPBACK,
    DevNoDockerConfig,
    build_arg_parser,
    build_env,
    resolve_config,
)
from scripts.dev_nodocker.runner import main, run
from scripts.dev_nodocker.services import (
    provision_mongo,
    provision_otel,
    provision_postgres,
    provision_redis,
    provision_temporal,
    teardown_redis,
)
from scripts.dev_nodocker.supervise import run_migrations, wait_for_health

__all__ = [
    "LOOPBACK",
    "DevNoDockerConfig",
    "build_arg_parser",
    "resolve_config",
    "build_env",
    "provision_postgres",
    "provision_redis",
    "provision_temporal",
    "provision_mongo",
    "provision_otel",
    "teardown_redis",
    "run_migrations",
    "wait_for_health",
    "run",
    "main",
]
