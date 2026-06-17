"""ASGI middleware that advertises the server's contract version on responses."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src._version import __version__

VERSION_HEADER = "x-agentex-version"


class VersionHeaderMiddleware:
    """Set `X-Agentex-Version` on every HTTP response so clients can detect a
    server whose contract version is incompatible with their build."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_version(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[VERSION_HEADER] = __version__
            await send(message)

        await self.app(scope, receive, send_with_version)
