"""
Pure ASGI middleware for health check responses.

This middleware intercepts health check requests at the ASGI level,
bypassing all Starlette/FastAPI middleware for maximum performance.

Health check endpoints:
- /healthz: Liveness probe - fast, no dependency checks (sub-millisecond)
- /readyz: Readiness probe - checks DB, Redis, MongoDB connectivity
- /healthcheck: Alias for readiness probe
"""

import asyncio
import json
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

# Liveness probes - fast, no dependency checks
LIVENESS_PATHS: frozenset[str] = frozenset({"/healthz"})

# Readiness probes - check dependencies
READINESS_PATHS: frozenset[str] = frozenset({"/readyz", "/healthcheck"})

# All health check paths
HEALTH_CHECK_PATHS: frozenset[str] = LIVENESS_PATHS | READINESS_PATHS

# Timeout for individual dependency checks (seconds)
DEPENDENCY_CHECK_TIMEOUT = 2.0

# Total timeout for all readiness checks (seconds)
READINESS_CHECK_TIMEOUT = 5.0


class HealthCheckInterceptor:
    """
    Pure ASGI middleware that intercepts health check requests
    before they reach the FastAPI middleware stack.

    Liveness (/healthz):
        Returns 200 immediately - used by Kubernetes to detect stuck processes.
        Sub-millisecond response time.

    Readiness (/readyz, /healthcheck):
        Checks database, Redis, and MongoDB connectivity.
        Returns 200 if all dependencies are healthy, 503 otherwise.
        Used by Kubernetes to decide whether to route traffic.

    Only GET requests are intercepted. Other methods fall through
    to FastAPI for proper 405 Method Not Allowed handling.
    """

    __slots__ = ("app",)

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope.get("method")

        # Handle liveness probe - fast path
        if path in LIVENESS_PATHS:
            if method == "GET":
                await self._send_response(send, 200, {"status": "ok"})
            else:
                await self._send_method_not_allowed(send)
            return

        # Handle readiness probe - check dependencies
        if path in READINESS_PATHS:
            if method == "GET":
                await self._handle_readiness_check(send)
            else:
                await self._send_method_not_allowed(send)
            return

        # Pass through to FastAPI
        await self.app(scope, receive, send)

    async def _handle_readiness_check(self, send: Send) -> None:
        """Check all dependencies and return appropriate status."""
        try:
            # Run all checks with overall timeout
            results = await asyncio.wait_for(
                self._check_all_dependencies(),
                timeout=READINESS_CHECK_TIMEOUT,
            )

            # Determine overall health
            all_healthy = all(r["healthy"] for r in results.values())
            status_code = 200 if all_healthy else 503

            response_body = {
                "status": "ok" if all_healthy else "degraded",
                "checks": results,
            }

            await self._send_response(send, status_code, response_body)

        except TimeoutError:
            await self._send_response(
                send,
                503,
                {
                    "status": "timeout",
                    "error": "Health check timed out",
                },
            )
        except Exception as e:
            await self._send_response(
                send,
                503,
                {
                    "status": "error",
                    "error": str(e),
                },
            )

    async def _check_all_dependencies(self) -> dict[str, dict[str, Any]]:
        """Check all dependencies concurrently."""
        # Import here to avoid circular imports and ensure dependencies are loaded
        from src.config.dependencies import GlobalDependencies

        deps = GlobalDependencies()

        # Run all checks concurrently
        postgres_task = self._check_postgres(deps)
        redis_task = self._check_redis(deps)
        mongodb_task = self._check_mongodb(deps)

        results = await asyncio.gather(
            postgres_task,
            redis_task,
            mongodb_task,
            return_exceptions=True,
        )

        return {
            "postgres": self._format_check_result(results[0]),
            "redis": self._format_check_result(results[1]),
            "mongodb": self._format_check_result(results[2]),
        }

    def _format_check_result(
        self, result: dict[str, Any] | Exception
    ) -> dict[str, Any]:
        """Format a check result, handling exceptions."""
        if isinstance(result, Exception):
            return {"healthy": False, "error": str(result)}
        return result

    async def _check_postgres(self, deps: Any) -> dict[str, Any]:
        """Check PostgreSQL connectivity."""
        from sqlalchemy import text

        try:
            engine = deps.database_async_read_write_engine
            if engine is None:
                return {"healthy": False, "error": "Engine not initialized"}

            async with asyncio.timeout(DEPENDENCY_CHECK_TIMEOUT):
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))

            return {"healthy": True}
        except TimeoutError:
            return {"healthy": False, "error": "Connection timeout"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_redis(self, deps: Any) -> dict[str, Any]:
        """Check Redis connectivity."""
        try:
            pool = deps.redis_pool
            if pool is None:
                return {"healthy": False, "error": "Pool not initialized"}

            import redis.asyncio as redis_lib

            async with asyncio.timeout(DEPENDENCY_CHECK_TIMEOUT):
                client = redis_lib.Redis(connection_pool=pool)
                await client.ping()

            return {"healthy": True}
        except TimeoutError:
            return {"healthy": False, "error": "Connection timeout"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_mongodb(self, deps: Any) -> dict[str, Any]:
        """Check MongoDB connectivity."""
        try:
            client = deps.mongodb_client
            if client is None:
                return {"healthy": False, "error": "Client not initialized"}

            # MongoDB client is synchronous, run in thread pool
            async with asyncio.timeout(DEPENDENCY_CHECK_TIMEOUT):
                await asyncio.to_thread(client.admin.command, "ping")

            return {"healthy": True}
        except TimeoutError:
            return {"healthy": False, "error": "Connection timeout"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _send_response(
        self, send: Send, status: int, body: dict[str, Any]
    ) -> None:
        """Send a JSON response."""
        body_bytes = json.dumps(body).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body_bytes)).encode()),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
            }
        )

    async def _send_method_not_allowed(self, send: Send) -> None:
        """Send 405 Method Not Allowed response."""
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
