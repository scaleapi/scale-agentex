"""
Unit tests for the HealthCheckInterceptor ASGI middleware.
Tests that health checks bypass the middleware stack.
"""

import pytest
from src.api.health_interceptor import HEALTH_CHECK_PATHS, HealthCheckInterceptor
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

    def test_intercepts_get_health_requests(self):
        """Test that GET requests to health paths are intercepted."""

        def should_not_be_called(request):
            raise AssertionError("Inner app should not be called for health checks")

        inner_app = Starlette(
            routes=[Route(path, should_not_be_called) for path in HEALTH_CHECK_PATHS]
        )
        wrapped_app = HealthCheckInterceptor(inner_app)

        client = TestClient(wrapped_app, raise_server_exceptions=True)

        for path in HEALTH_CHECK_PATHS:
            response = client.get(path)
            assert response.status_code == 200
            assert response.content == b""

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

    def test_passes_through_post_to_health_paths(self):
        """Test that POST to health paths passes through for 405 handling."""

        def method_handler(request):
            return PlainTextResponse("Method handler called", status_code=200)

        inner_app = Starlette(
            routes=[Route("/healthcheck", method_handler, methods=["POST"])]
        )
        wrapped_app = HealthCheckInterceptor(inner_app)

        client = TestClient(wrapped_app)
        response = client.post("/healthcheck")
        assert response.status_code == 200
        assert response.content == b"Method handler called"

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
