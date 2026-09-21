"""Reused HTTP clients forward the current request ID, never a cached value."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from src.adapters.http.adapter_httpx import HttpxGateway
from src.utils import cached_httpx_client
from src.utils.logging import ctx_var_request_id

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fallback", [False, True])
async def test_cached_auth_client_uses_each_request_context(monkeypatch, fallback):
    seen = {}
    real_client = httpx.AsyncClient

    async def handler(request):
        await asyncio.sleep(0)
        seen[request.url.path] = request.headers.get("x-request-id")
        return httpx.Response(200, json={})

    def create_client(**kwargs):
        if fallback and kwargs.get("http2"):
            raise ImportError("optional HTTP/2 dependency unavailable")
        return real_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cached_httpx_client.httpx, "AsyncClient", create_client)
    cached_httpx_client.get_async_client.cache_clear()
    client = cached_httpx_client.get_async_client("http://auth")

    async def request(path, request_id, headers=None):
        token = ctx_var_request_id.set(request_id)
        try:
            await client.post(path, headers=headers)
        finally:
            ctx_var_request_id.reset(token)

    try:
        await asyncio.gather(request("/a", "request-a"), request("/b", "request-b"))
        await request("/explicit", "ambient", {"x-request-id": "explicit"})
        await request("/none", None)
    finally:
        await client.aclose()
        cached_httpx_client.get_async_client.cache_clear()
    assert seen == {
        "/a": "request-a",
        "/b": "request-b",
        "/explicit": "explicit",
        "/none": None,
    }


@pytest.mark.parametrize("streaming", [False, True])
async def test_gateway_clients_forward_request_id(monkeypatch, streaming):
    seen = []
    real_client = httpx.AsyncClient

    async def handler(request):
        seen.append(request.headers.get("x-request-id"))
        return httpx.Response(200, json={"ok": True})

    def create_client(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", create_client)
    monkeypatch.setattr(HttpxGateway, "_regular_client", None)
    monkeypatch.setattr(HttpxGateway, "_streaming_client", None)
    monkeypatch.setattr(
        HttpxGateway,
        "_environment_variables",
        SimpleNamespace(
            HTTPX_MAX_CONNECTIONS=10,
            HTTPX_MAX_KEEPALIVE_CONNECTIONS=5,
            HTTPX_CONNECT_TIMEOUT=1,
            HTTPX_READ_TIMEOUT=1,
            HTTPX_WRITE_TIMEOUT=1,
            HTTPX_POOL_TIMEOUT=1,
            HTTPX_STREAMING_READ_TIMEOUT=1,
        ),
    )
    gateway = HttpxGateway.__new__(HttpxGateway)
    token = ctx_var_request_id.set("gateway-request")
    try:
        if streaming:
            assert [
                chunk async for chunk in gateway.stream_call("POST", "http://agent")
            ] == [{"ok": True}]
        else:
            assert await gateway.async_call("POST", "http://agent") == {"ok": True}
    finally:
        ctx_var_request_id.reset(token)
        await HttpxGateway.close_clients()
    assert seen == ["gateway-request"]
