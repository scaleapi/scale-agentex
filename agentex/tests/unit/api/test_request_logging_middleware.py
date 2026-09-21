"""Request IDs survive streaming and do not escape their request."""

import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, Request
from src.api.app import handle_unexpected
from src.api.RequestLoggingMiddleware import RequestLoggingMiddleware
from src.utils.logging import ctx_var_request_id
from starlette.responses import StreamingResponse

pytestmark = pytest.mark.unit


def make_scope(value=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "GET",
        "path": "/example",
        "root_path": "",
        "query_string": b"",
        "headers": [] if value is None else [(b"x-request-id", value)],
    }


async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}


@pytest.mark.parametrize(
    "inbound",
    [
        b"upstream-123",
        b"a" * 128,
        None,
        b"",
        b"bad value",
        b"bad\nvalue",
        b"\xff",
        b"a" * 129,
    ],
)
async def test_preserves_valid_ids_and_generates_invalid_ones(inbound):
    sent = []
    observed = []

    async def endpoint(scope, receive, send):
        observed.append((ctx_var_request_id.get(), scope["state"]["request_id"]))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        sent.append(message)

    token = ctx_var_request_id.set("outer-context")
    try:
        scope = make_scope(inbound)
        await RequestLoggingMiddleware(endpoint)(scope, receive, send)
        assert ctx_var_request_id.get() == "outer-context"
    finally:
        ctx_var_request_id.reset(token)
    chosen = observed[0][0]
    assert observed == [(chosen, chosen)]
    if inbound in (b"upstream-123", b"a" * 128):
        assert chosen == inbound.decode()
    else:
        assert UUID(chosen).version == 4
    assert (b"x-request-id", chosen.encode()) in sent[0]["headers"]
    assert (b"x-request-id", chosen.encode()) in scope["headers"]


async def test_stream_context_is_kept_until_complete_and_isolated_between_requests():
    observed = []

    async def endpoint(scope, receive, send):
        async def body():
            for _ in range(2):
                await asyncio.sleep(0)
                observed.append(
                    (scope["state"]["request_id"], ctx_var_request_id.get())
                )
                yield "chunk"

        await StreamingResponse(body())(scope, receive, send)

    async def send(message):
        pass

    async def run(value):
        await RequestLoggingMiddleware(endpoint)(make_scope(value), receive, send)
        assert ctx_var_request_id.get(None) is None

    await asyncio.gather(run(b"request-a"), run(b"request-b"))
    assert (
        sorted(observed)
        == [("request-a", "request-a")] * 2 + [("request-b", "request-b")] * 2
    )


@pytest.mark.parametrize("exception", [RuntimeError, asyncio.CancelledError])
async def test_request_context_resets_after_failure(exception):
    async def endpoint(scope, receive, send):
        raise exception("interrupted")

    async def send(message):
        pass

    with pytest.raises(exception):
        await RequestLoggingMiddleware(endpoint)(make_scope(b"failed"), receive, send)
    assert ctx_var_request_id.get(None) is None


async def test_unhandled_error_echoes_request_id_and_logs_it(caplog):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(Exception, handle_unexpected)

    @app.get("/failure")
    async def failure(request: Request):
        raise RuntimeError("test failure")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/failure", headers={"x-request-id": "error-123"})
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "error-123"
    assert any(
        getattr(record, "request_id", None) == "error-123" for record in caplog.records
    )
    assert ctx_var_request_id.get(None) is None
