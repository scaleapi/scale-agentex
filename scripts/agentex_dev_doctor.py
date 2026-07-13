#!/usr/bin/env python3
"""Preflight checks before Agentex local development (./dev.sh / make dev).

Addresses onboarding failures when Docker, uv, or port conflicts block OSS contributors
(see scaleapi/scale-agentex#163).

Usage:
  python scripts/agentex_dev_doctor.py
  python scripts/agentex_dev_doctor.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "agentex" / "docker-compose.yml"
PRIVATE_ECR_MARKERS = ("amazonaws.com", "dkr.ecr.")


def _check_cmd(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {
        "name": f"cmd_{name}",
        "passed": path is not None,
        "detail": path or f"{name} not found on PATH",
    }


def _check_docker_daemon() -> dict[str, Any]:
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {"name": "docker_daemon", "passed": True, "detail": "docker daemon reachable"}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"name": "docker_daemon", "passed": False, "detail": f"docker info failed: {exc}"}


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _check_ports() -> list[dict[str, Any]]:
    ports = {
        6379: "redis (stop local redis: brew services stop redis)",
        5432: "postgres",
        5003: "agentex API",
    }
    gates = []
    for port, label in ports.items():
        ok = _port_free(port)
        gates.append(
            {
                "name": f"port_{port}",
                "passed": ok,
                "detail": f"{label} port {port} available" if ok else f"{label} port {port} in use",
            }
        )
    return gates


def _check_docker_registry_env() -> dict[str, Any]:
    reg = os.environ.get("DOCKER_REGISTRY", "")
    if not reg:
        return {
            "name": "docker_registry",
            "passed": True,
            "detail": "DOCKER_REGISTRY unset — public python/node base images used",
        }
    if any(marker in reg for marker in PRIVATE_ECR_MARKERS):
        return {
            "name": "docker_registry",
            "passed": False,
            "detail": (
                f"DOCKER_REGISTRY={reg!r} points at private ECR; "
                "unset for OSS local dev (see docs/LOCAL_DEV.md)"
            ),
        }
    return {
        "name": "docker_registry",
        "passed": True,
        "detail": f"DOCKER_REGISTRY={reg!r}",
        "warn": True,
    }


def _check_compose_file() -> dict[str, Any]:
    ok = COMPOSE_FILE.is_file()
    return {
        "name": "compose_file",
        "passed": ok,
        "detail": str(COMPOSE_FILE) if ok else "agentex/docker-compose.yml missing",
    }


def run_doctor() -> dict[str, Any]:
    gates: list[dict[str, Any]] = [
        _check_cmd("docker"),
        _check_cmd("uv"),
        _check_docker_daemon(),
        _check_compose_file(),
        _check_docker_registry_env(),
        * _check_ports(),
    ]
    active = [g for g in gates if not g.get("warn")]
    passed = all(g["passed"] for g in active)
    return {"repo": str(REPO_ROOT), "gates": gates, "passed": passed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agentex local dev preflight")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_doctor()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Agentex dev doctor — {'PASS' if report['passed'] else 'FAIL'}")
        for gate in report["gates"]:
            mark = "PASS" if gate["passed"] else "FAIL"
            if gate.get("warn"):
                mark = "WARN"
            print(f"  [{mark}] {gate['name']}: {gate['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
