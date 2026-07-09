"""Subprocess supervision: spawn/stream children, wait for readiness, migrate, terminate."""

from __future__ import annotations

import asyncio
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from scripts.dev_local.config import LOOPBACK, DevLocalConfig

logger = logging.getLogger(__name__)


async def stream_output(proc: asyncio.subprocess.Process, prefix: str) -> None:
    """Stream a child's combined stdout/stderr with a prefix until EOF."""
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        print(f"[{prefix}] {line.decode(errors='replace').rstrip()}", flush=True)


async def spawn(
    name: str, cmd: list[str], cwd: Path, env: dict[str, str]
) -> asyncio.subprocess.Process:
    logger.info("Starting %s: %s", name, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    asyncio.create_task(stream_output(proc, name))
    return proc


async def wait_for_port(
    proc: asyncio.subprocess.Process | None,
    host: str,
    port: int,
    timeout: float = 30.0,
) -> bool:
    """Wait until a TCP port accepts connections, or the process dies, or timeout.

    The process-alive check avoids a false positive where our launch failed (e.g. the
    port was already taken by a leftover) but something else answers on it.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if proc is not None and proc.returncode is not None:
            return False
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return True
        except OSError:
            await asyncio.sleep(0.5)
    return False


async def run_migrations(cfg: DevLocalConfig, env: dict[str, str]) -> None:
    """Run `alembic upgrade head` from the migrations dir (sync psycopg2 engine)."""
    migrations_dir = cfg.agentex_dir / "database" / "migrations"
    logger.info("Running database migrations ...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        "head",
        cwd=str(migrations_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    await stream_output(proc, "alembic")
    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"alembic upgrade head failed (exit {rc})")


def _probe(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 - localhost only
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


async def wait_for_health(port: int, timeout: float = 90.0) -> bool:
    """Poll /healthz (liveness) until 200 or timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    url = f"http://{LOOPBACK}:{port}/healthz"
    while loop.time() < deadline:
        if await loop.run_in_executor(None, _probe, url):
            return True
        await asyncio.sleep(1.0)
    return False


async def terminate(
    proc: asyncio.subprocess.Process, name: str, grace: float = 5.0
) -> None:
    if proc.returncode is not None:
        return
    logger.info("Stopping %s ...", name)
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace)
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
