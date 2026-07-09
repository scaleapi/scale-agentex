"""Resolve an agent's registered ACP URL to one the backend can actually reach.

Agents register their ACP URL as ``http://host.docker.internal:<port>`` (the SDK
default) so that a **Docker-based** backend can reach an agent process running on
the host. When the backend itself runs directly on the host — i.e. the docker-free
local dev mode (``./dev.sh local`` / ``python -m scripts.dev_local``) — ``host.docker.internal``
does not resolve, and every ACP call fails with
``[Errno 8] nodename nor servname provided, or not known``.

The correct address depends on the *backend's* network topology, which only the
backend knows. So the runner (``scripts.dev_local``) sets ``AGENTEX_ACP_HOST_OVERRIDE``
(to ``127.0.0.1``) and the backend rewrites the Docker-only sentinel host to that
value wherever it dials an agent. When the env var is unset (Docker / staging /
prod), this is a no-op and the stored URL is used verbatim.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from src.utils.logging import make_logger

logger = make_logger(__name__)

# The hostname Docker Desktop injects so a container can reach the host. It does
# not resolve for a process running directly on the host.
_DOCKER_HOST_SENTINEL = "host.docker.internal"

# Env var the local (no-Docker) runner sets to the host address agents are actually
# reachable at (e.g. 127.0.0.1). Unset everywhere else, making resolution a no-op.
_ACP_HOST_OVERRIDE_ENV = "AGENTEX_ACP_HOST_OVERRIDE"


def resolve_acp_url(url: str) -> str:
    """Rewrite a ``host.docker.internal`` ACP host to the local override, if set.

    Returns the URL unchanged when the override env var is unset or the URL does
    not use the Docker sentinel host, so it is safe to call on every ACP dial.
    """
    override = os.environ.get(_ACP_HOST_OVERRIDE_ENV)
    if not override or not url:
        return url

    parts = urlsplit(url)
    if parts.hostname != _DOCKER_HOST_SENTINEL:
        return url

    netloc = f"{override}:{parts.port}" if parts.port is not None else override
    rewritten = urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    )
    logger.info(
        "Rewriting ACP host for local (no-Docker) mode: %s -> %s", url, rewritten
    )
    return rewritten
