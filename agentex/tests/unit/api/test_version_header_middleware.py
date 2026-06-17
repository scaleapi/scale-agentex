"""Unit tests for VersionHeaderMiddleware — sets X-Agentex-Version on responses."""

import pytest
from src._version import __version__
from src.api.version_header_middleware import VERSION_HEADER, VersionHeaderMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


@pytest.mark.unit
def test_sets_version_header_on_responses():
    def endpoint(request):
        return PlainTextResponse("ok")

    wrapped = VersionHeaderMiddleware(Starlette(routes=[Route("/x", endpoint)]))
    client = TestClient(wrapped)

    response = client.get("/x")
    assert response.status_code == 200
    assert response.headers[VERSION_HEADER] == __version__
