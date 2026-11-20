from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from src.api import authentication_middleware
from src.api.authentication_cache import AuthenticationCache
from src.api.authentication_middleware import AgentexAuthMiddleware
from src.config.environment_variables import EnvVarKeys

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
async def gateway_client(monkeypatch, tmp_path):
    token_path = tmp_path / "token"
    token_path.write_text("pod-secret")
    monkeypatch.setenv("AGENTEX_AUTH_SA_TOKEN_PATH", str(token_path))
    configuration = {
        EnvVarKeys.AGENTEX_AUTH_URL: "https://auth.example",
        EnvVarKeys.ENVIRONMENT: "production",
    }
    monkeypatch.setattr(
        authentication_middleware,
        "resolve_environment_variable_dependency",
        configuration.get,
    )
    cache = AuthenticationCache()
    monkeypatch.setattr(
        authentication_middleware, "get_auth_cache", AsyncMock(return_value=cache)
    )
    provider_status = {"code": 200, "headers": {}}
    provider_requests = []

    def handle(request):
        provider_requests.append(request)
        if provider_status["code"] == "timeout":
            raise httpx.ReadTimeout("user-secret pod-secret", request=request)
        if provider_status["code"] != 200:
            return httpx.Response(
                provider_status["code"],
                headers=provider_status["headers"],
                json={"detail": "user-secret pod-secret"},
            )
        return httpx.Response(200, json={"user_id": "user"})

    app = FastAPI()
    app.add_middleware(AgentexAuthMiddleware)
    served = []

    @app.get("/protected")
    async def protected(request: Request):
        served.append(request.state.principal_context)
        return {"principal": request.state.principal_context}

    async with httpx.AsyncClient(
        base_url="https://auth.example", transport=httpx.MockTransport(handle)
    ) as provider:
        monkeypatch.setattr(
            "src.utils.http_request_handler.get_async_client", lambda _: provider
        )
        async with httpx.AsyncClient(
            base_url="https://agentex.example",
            transport=httpx.ASGITransport(app=app),
            headers={"authorization": "Bearer user-secret"},
        ) as client:
            yield client, token_path, provider_status, provider_requests, served


async def test_valid_user_reaches_protected_route(gateway_client):
    client, _, _, provider_requests, served = gateway_client

    response = await client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"principal": {"user_id": "user"}}
    assert len(provider_requests) == 1
    assert served == [{"user_id": "user"}]


@pytest.mark.parametrize("provider_failure", [500, 502, 503, 504, 307, "timeout"])
async def test_provider_unavailable_remains_retryable_and_is_not_cached(
    gateway_client, provider_failure, caplog
):
    client, _, provider_status, provider_requests, served = gateway_client
    provider_status["code"] = provider_failure

    response = await client.get("/protected")

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}
    assert not served
    assert "user-secret" not in caplog.text
    assert "pod-secret" not in caplog.text
    assert "[REDACTED]" not in caplog.text

    provider_status["code"] = 200
    recovered = await client.get("/protected")
    assert recovered.status_code == 200
    assert len(provider_requests) == 2


async def test_unreadable_pod_token_returns_503_at_request_boundary(
    gateway_client, monkeypatch, caplog
):
    client, token_path, _, provider_requests, served = gateway_client

    def unreadable_token(*args, **kwargs):
        raise PermissionError(f"user-secret pod-secret at {token_path}")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", unreadable_token)
        response = await client.get("/protected")

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}
    assert not provider_requests
    assert not served
    for sensitive in ("user-secret", "pod-secret", str(token_path)):
        assert sensitive not in caplog.text
        assert sensitive not in response.text

    recovered = await client.get("/protected")
    assert recovered.status_code == 200
    assert len(provider_requests) == 1


async def test_bad_user_credentials_still_return_401(gateway_client, caplog):
    client, _, provider_status, provider_requests, served = gateway_client
    provider_status["code"] = 401

    response = await client.get("/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert len(provider_requests) == 1
    assert not served
    assert "user-secret" not in caplog.text
    assert "pod-secret" not in caplog.text


async def test_bad_user_credentials_log_provider_status(gateway_client, caplog):
    client, _, provider_status, _, _ = gateway_client
    provider_status["code"] = 401

    await client.get("/protected")

    assert "AuthenticationError (status 401)" in caplog.text
    assert "[REDACTED]" in caplog.text


@pytest.mark.parametrize("status", [401, 403])
async def test_service_account_rejection_returns_503(gateway_client, status, caplog):
    client, _, provider_status, provider_requests, served = gateway_client
    provider_status["code"] = status
    provider_status["headers"] = {"X-Service-Account-Auth-Error": "forbidden"}

    response = await client.get("/protected")

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}
    assert not served
    assert f"X-Service-Account-Auth-Error=forbidden (status {status})" in caplog.text
    assert "user-secret" not in caplog.text
    assert "pod-secret" not in caplog.text

    provider_status["code"] = 200
    recovered = await client.get("/protected")
    assert recovered.status_code == 200
    assert len(provider_requests) == 2
