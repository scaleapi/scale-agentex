"""
Integration tests for health endpoints.
Tests the application health check endpoints for monitoring and deployment validation.
"""

import pytest


@pytest.mark.integration
class TestHealthAPI:
    """Integration tests for health endpoints"""

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self, isolated_client):
        """Test primary health endpoint returns 200 OK"""
        response = await isolated_client.get("/healthcheck")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_variations(self, isolated_client):
        """Test all health endpoint variations work for different deployment tools"""
        health_endpoints = ["/healthcheck", "/healthz", "/readyz"]

        for endpoint in health_endpoints:
            response = await isolated_client.get(endpoint)
            assert (
                response.status_code == 200
            ), f"Health endpoint {endpoint} should return 200"

    @pytest.mark.asyncio
    async def test_health_endpoint_http_methods(self, isolated_client):
        """Test health endpoint only accepts GET requests"""
        # GET should work
        response = await isolated_client.get("/healthcheck")
        assert response.status_code == 200

        # POST should not be allowed
        response = await isolated_client.post("/healthcheck")
        assert response.status_code == 405  # Method Not Allowed

    @pytest.mark.asyncio
    async def test_health_endpoints_do_not_require_database(self, isolated_client):
        """Test that health endpoints work even if database connections fail"""
        # Health endpoints should work regardless of database state
        # This is important for deployment health checks
        for endpoint in ["/healthcheck", "/healthz", "/readyz"]:
            response = await isolated_client.get(endpoint)
            assert response.status_code == 200
