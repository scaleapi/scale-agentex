"""
Pure ASGI middleware for fast health check responses.

This middleware intercepts health check requests at the ASGI level,
bypassing all Starlette/FastAPI middleware for maximum performance.
Kubernetes probes hit these endpoints frequently, so sub-millisecond
response time is critical.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

HEALTH_CHECK_PATHS: frozenset[str] = frozenset(
    {
        "/healthcheck",
        "/healthz",
        "/readyz",
    }
)


class HealthCheckInterceptor:
    """
    Pure ASGI middleware that intercepts health check requests
    before they reach the FastAPI middleware stack.

    This provides sub-millisecond response times for Kubernetes probes
    by avoiding BaseHTTPMiddleware task group overhead, logging,
    and request body parsing.

    Only GET requests are intercepted. Other methods fall through
    to FastAPI for proper 405 Method Not Allowed handling.
    """

    __slots__ = ("app",)

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] in HEALTH_CHECK_PATHS:
            if scope.get("method") == "GET":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                    }
                )
                return
            else:
                # Return 405 Method Not Allowed for non-GET requests
                await send(
                    {
                        "type": "http.response.start",
                        "status": 405,
                        "headers": [(b"allow", b"GET")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                    }
                )
                return

        await self.app(scope, receive, send)
