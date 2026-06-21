"""Resolve a channel binding's task params from a configured remote source.

A route binding can carry a ``params_source``: a URL the channel GETs at dispatch
time to obtain the opaque params forwarded to ``task/create``. This keeps the channel
layer generic — it fetches and forwards params without interpreting them. The source
endpoint owns whatever mapping produces those params; the channel never learns what
they mean.

Response shape (lenient)::

    { "params": { ... }, "task_metadata": { ... } }   # task_metadata optional

A bare JSON object with no ``params`` key is treated as the params dict itself.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from src.domain.channels.base import ChannelBinding
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Injectable fetcher: url -> response JSON. Default uses httpx; tests inject a fake.
ParamsFetcher = Callable[[str], Awaitable[dict[str, Any]]]

# Optional generic auth header sent when fetching a params source, configured via env
# so no credential is hard-coded. JSON object of header name -> value, e.g.
# CHANNELS_PARAMS_SOURCE_HEADERS='{"x-api-key": "...", "x-selected-account-id": "..."}'.
# The channel forwards these opaquely — it does not interpret what they mean.
_AUTH_HEADERS_ENV = "CHANNELS_PARAMS_SOURCE_HEADERS"


class ParamsSourceError(RuntimeError):
    """Raised when a binding's params_source cannot be resolved."""


async def _default_fetch(url: str) -> dict[str, Any]:
    """GET the params source over HTTP. Imported lazily so inline-only bindings carry
    no httpx dependency."""
    import json as _json

    import httpx

    headers = {"accept": "application/json"}
    raw_headers = os.environ.get(_AUTH_HEADERS_ENV)
    if raw_headers:
        try:
            extra = _json.loads(raw_headers)
        except _json.JSONDecodeError:
            raise ParamsSourceError(f"{_AUTH_HEADERS_ENV} is not valid JSON") from None
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items()})

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        # Covers connection/timeout (RequestError) and non-2xx (HTTPStatusError) so
        # the route handler's ParamsSourceError catch logs + returns a clean 500.
        raise ParamsSourceError(f"params source request failed: {exc}") from exc
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise ParamsSourceError(f"params source returned invalid JSON: {exc}") from exc


async def resolve_binding_params(
    binding: ChannelBinding, *, fetch: ParamsFetcher | None = None
) -> ChannelBinding:
    """Populate ``binding.params`` from its ``params_source`` when set.

    Precedence: a binding with a ``params_source`` fetches its params remotely. A
    binding with only inline ``params`` is returned untouched. Any ``task_metadata``
    the source returns is captured for stamping on the task. Mutates and returns the
    same binding.
    """
    if not binding.params_source:
        return binding

    do_fetch = fetch or _default_fetch
    payload = await do_fetch(binding.params_source)
    if not isinstance(payload, dict):
        raise ParamsSourceError("params source returned a non-object response")

    metadata = payload.get("task_metadata")
    if isinstance(metadata, dict):
        binding.extra_task_metadata = {str(k): str(v) for k, v in metadata.items()}

    params = payload.get("params")
    if isinstance(params, dict):
        binding.params = params
    else:
        # Lenient: a bare object with no "params" key is the params dict itself —
        # minus a top-level task_metadata, which is captured above, not a param.
        binding.params = {k: v for k, v in payload.items() if k != "task_metadata"}

    logger.info("[channels] resolved remote params for agent %s", binding.agent_name)
    return binding
