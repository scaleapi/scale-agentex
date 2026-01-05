"""
Unit tests for the HealthCheckInterceptor ASGI middleware.
Tests that health checks bypass the middleware stack.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.api.health_interceptor import (
    HEALTH_CHECK_PATHS,
    LIVENESS_PATHS,
    READINESS_PATHS,
    HealthCheckInterceptor,
)
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


@pytest.mark.unit
class TestHealthCheckInterceptor:
    """Unit tests for HealthCheckInterceptor."""

    def test_health_paths_constant(self):
        """Verify all expected health paths are defined."""
        expected_paths = {"/healthcheck", "/healthz", "/readyz"}
        assert HEALTH_CHECK_PATHS == expected_paths

    def test_liveness_paths_constant(self):
        """Verify liveness paths are defined correctly."""
        assert LIVENESS_PATHS == {"/healthz"}

    def test_readiness_paths_constant(self):
        """Verify readiness paths are defined correctly."""
        assert READINESS_PATHS == {"/readyz", "/healthcheck"}

    def test_liveness_returns_200_without_dependencies(self):
        """Test that liveness probe (/healthz) returns 200 without checking deps."""

        def should_not_be_called(request):
            raise AssertionError("Inner app should not be called for health checks")

        inner_app = Starlette(
            routes=[Route(path, should_not_be_called) for path in LIVENESS_PATHS]
        )
        wrapped_app = HealthCheckInterceptor(inner_app)

        client = TestClient(wrapped_app, raise_server_exceptions=True)

        for path in LIVENESS_PATHS:
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_readiness_returns_503_when_dependencies_unavailable(self):
        """Test that readiness probes return 503 when dependencies aren't initialized."""

        def should_not_be_called(request):
            raise AssertionError("Inner app should not be called for health checks")

        inner_app = Starlette(
            routes=[Route(path, should_not_be_called) for path in READINESS_PATHS]
        )
        wrapped_app = HealthCheckInterceptor(inner_app)

        # Mock GlobalDependencies to return None for all dependencies
        mock_deps = MagicMock()
        mock_deps.database_async_read_write_engine = None
        mock_deps.redis_pool = None
        mock_deps.mongodb_client = None

        with patch(
            "src.config.dependencies.GlobalDependencies", return_value=mock_deps
        ):
            client = TestClient(wrapped_app, raise_server_exceptions=True)

            for path in READINESS_PATHS:
                response = client.get(path)
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "degraded"
                assert "checks" in data

    def test_readiness_returns_200_when_all_dependencies_healthy(self):
        """Test that readiness probes return 200 when all dependencies are healthy."""

        def should_not_be_called(request):
            raise AssertionError("Inner app should not be called for health checks")

        inner_app = Starlette(
            routes=[Route(path, should_not_be_called) for path in READINESS_PATHS]
        )
        wrapped_app = HealthCheckInterceptor(inner_app)

        # Mock healthy dependencies
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_engine.connect = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            )
        )

        mock_redis_pool = MagicMock()

        mock_mongodb_client = MagicMock()
        mock_mongodb_client.admin.command = MagicMock(return_value={"ok": 1})

        mock_deps = MagicMock()
        mock_deps.database_async_read_write_engine = mock_engine
        mock_deps.redis_pool = mock_redis_pool
        mock_deps.mongodb_client = mock_mongodb_client

        with (
            patch("src.config.dependencies.GlobalDependencies", return_value=mock_deps),
            patch("redis.asyncio.Redis") as mock_redis_class,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping = AsyncMock()
            mock_redis_class.return_value = mock_redis_instance

            client = TestClient(wrapped_app, raise_server_exceptions=True)

            for path in READINESS_PATHS:
                response = client.get(path)
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["checks"]["postgres"]["healthy"] is True
                assert data["checks"]["redis"]["healthy"] is True
                assert data["checks"]["mongodb"]["healthy"] is True

    def test_passes_through_non_health_requests(self):
        """Test that non-health requests pass through to inner app."""

        def test_endpoint(request):
            return PlainTextResponse("OK")

        inner_app = Starlette(routes=[Route("/test", test_endpoint)])
        wrapped_app = HealthCheckInterceptor(inner_app)

        client = TestClient(wrapped_app)
        response = client.get("/test")
        assert response.status_code == 200
        assert response.content == b"OK"

    def test_returns_405_for_non_get_health_requests(self):
        """Test that non-GET requests to health paths return 405."""

        def should_not_be_called(request):
            raise AssertionError(
                "Inner app should not be called for health check paths"
            )

        inner_app = Starlette(
            routes=[
                Route("/healthcheck", should_not_be_called, methods=["POST", "PUT"])
            ]
        )
        wrapped_app = HealthCheckInterceptor(inner_app)

        client = TestClient(wrapped_app, raise_server_exceptions=True)

        for path in HEALTH_CHECK_PATHS:
            for method in ["post", "put", "delete", "patch"]:
                response = getattr(client, method)(path)
                assert response.status_code == 405
                assert response.headers.get("allow") == "GET"
                assert response.content == b""

    def test_passes_through_websocket_connections(self):
        """Test that WebSocket connections pass through."""

        async def websocket_endpoint(websocket):
            await websocket.accept()
            await websocket.send_text("hello")
            await websocket.close()

        from starlette.routing import WebSocketRoute

        inner_app = Starlette(routes=[WebSocketRoute("/ws", websocket_endpoint)])
        wrapped_app = HealthCheckInterceptor(inner_app)

        client = TestClient(wrapped_app)
        with client.websocket_connect("/ws") as websocket:
            data = websocket.receive_text()
            assert data == "hello"
