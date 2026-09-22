"""Request and stream logs contain metadata, not user payloads."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Request, Response
from pydantic import BaseModel
from src.adapters.http.adapter_httpx import HttpxGateway
from src.adapters.streams.adapter_redis import RedisStreamRepository
from src.api.logged_api_route import log_request, log_response
from src.domain.entities.agents_rpc import AgentRPCMethod
from src.domain.services.agent_acp_service import AgentACPService
from src.utils.logging import LOG_FORMAT

pytestmark = pytest.mark.unit
PAYLOAD = "private-user-payload-marker"


def test_request_and_response_logs_omit_payload_headers_and_query(caplog):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/tasks/actual-id",
            "root_path": "",
            "route": SimpleNamespace(path="/tasks/{task_id}"),
            "query_string": f"q={PAYLOAD}".encode(),
            "headers": [(b"x-user-data", PAYLOAD.encode())],
        }
    )
    with caplog.at_level(logging.INFO):
        log_request("request-1", request, json.dumps({"prompt": PAYLOAD}).encode())
        log_response("request-1", request, Response(headers={"x-user-data": PAYLOAD}))
    assert len(caplog.records) == 2
    assert PAYLOAD not in str([record.__dict__ for record in caplog.records])
    for record in caplog.records:
        assert record.request_id == "request-1"
        assert record.path == "/tasks/{task_id}"
        assert not {"body", "headers", "query_params"}.intersection(record.__dict__)
    rendered = [
        logging.Formatter(LOG_FORMAT).format(record) for record in caplog.records
    ]
    assert "POST /tasks/{task_id}" in rendered[0]
    assert "200" in rendered[1]
    assert all("request-1" in line for line in rendered)


async def test_redis_publish_logs_no_payload(caplog):
    repository = RedisStreamRepository.__new__(RedisStreamRepository)
    repository.redis = SimpleNamespace(xadd=AsyncMock(return_value=b"1-0"))
    repository.environment_variables = SimpleNamespace(
        REDIS_STREAM_TTL_SECONDS=0, REDIS_STREAM_MAXLEN=100
    )
    repository.send_redis_connection_metrics = AsyncMock()
    data = {"prompt": PAYLOAD}
    with caplog.at_level(logging.INFO):
        assert await repository.send_data("task:test", data) == b"1-0"
    assert PAYLOAD not in str([record.__dict__ for record in caplog.records])
    assert json.loads(repository.redis.xadd.call_args.kwargs["fields"]["data"]) == data


def test_acp_validation_logs_no_response_input(caplog):
    service = AgentACPService.__new__(AgentACPService)
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        service._parse_task_message({"type": "text", "content": {"prompt": PAYLOAD}})
    assert caplog.records
    assert PAYLOAD not in str([record.__dict__ for record in caplog.records])


async def test_acp_stream_logs_no_payload(caplog):
    class Params(BaseModel):
        prompt: str

    seen = []

    class Gateway:
        async def stream_call(self, **kwargs):
            seen.append(kwargs["payload"]["params"])
            yield {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}

    service = AgentACPService.__new__(AgentACPService)
    service._http_gateway = Gateway()
    with caplog.at_level(logging.INFO):
        result = [
            chunk
            async for chunk in service._call_jsonrpc_stream(
                "http://agent", AgentRPCMethod.MESSAGE_SEND, Params(prompt=PAYLOAD)
            )
        ]
    assert result == [{"ok": True}]
    assert seen == [{"prompt": PAYLOAD}]
    assert PAYLOAD not in str([record.__dict__ for record in caplog.records])


async def test_httpx_invalid_stream_line_is_not_logged(monkeypatch, caplog):
    async def handler(request):
        return httpx.Response(200, text=PAYLOAD + '\n{"ok": true}\n')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(HttpxGateway, "_streaming_client", client)
        gateway = HttpxGateway.__new__(HttpxGateway)
        with caplog.at_level(logging.INFO):
            result = [
                chunk async for chunk in gateway.stream_call("POST", "http://agent/api")
            ]
    assert result == [{"ok": True}]
    assert PAYLOAD not in str([record.__dict__ for record in caplog.records])


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "error_type",
    [httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout, ValueError],
)
async def test_http_errors_keep_diagnostics_without_payload(
    monkeypatch, caplog, streaming, error_type
):
    def handler(request):
        if error_type is httpx.HTTPStatusError:
            return httpx.Response(500, text=PAYLOAD)
        raise error_type(PAYLOAD)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(HttpxGateway, "_regular_client", client)
        monkeypatch.setattr(HttpxGateway, "_streaming_client", client)
        gateway = HttpxGateway.__new__(HttpxGateway)
        with caplog.at_level(logging.ERROR), pytest.raises(error_type) as exc:
            if streaming:
                _ = [
                    chunk
                    async for chunk in gateway.stream_call(
                        "POST", f"http://agent/{PAYLOAD}"
                    )
                ]
            else:
                await gateway.async_call("POST", f"http://agent/{PAYLOAD}")
    assert PAYLOAD in str(exc.value)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert PAYLOAD not in str(record.__dict__)
    assert "POST" in record.getMessage()
    assert error_type.__name__ in record.getMessage()
    if error_type is httpx.HTTPStatusError:
        assert "500" in record.getMessage()
