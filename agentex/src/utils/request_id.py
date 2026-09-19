"""Forward the active request ID without storing it on shared HTTP clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.utils.logging import ctx_var_request_id

if TYPE_CHECKING:
    import httpx


def forward_request_id(request: httpx.Request) -> None:
    request_id = ctx_var_request_id.get(None)
    if request_id and "x-request-id" not in request.headers:
        request.headers["x-request-id"] = request_id


async def forward_async_request_id(request: httpx.Request) -> None:
    forward_request_id(request)
