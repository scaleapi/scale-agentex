import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from src.adapters.authentication.adapter_agentex_authn_proxy import (
    AgentexAuthenticationProxy,
)
from src.adapters.authentication.exceptions import (
    AuthenticationServiceUnavailableError,
)
from src.adapters.authentication.service_account_token import (
    SERVICE_ACCOUNT_TOKEN_HEADER,
    agentex_auth_headers,
)
from src.adapters.authorization.adapter_agentex_authz_proxy import (
    AgentexAuthorizationProxy,
)
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.exceptions import ServiceError
from src.utils.http_request_handler import HttpRequestHandler

pytestmark = pytest.mark.unit


@pytest.fixture
def token_path(tmp_path, monkeypatch):
    path = tmp_path / "token"
    monkeypatch.setenv("AGENTEX_AUTH_SA_TOKEN_PATH", str(path))
    return path


@pytest.fixture
async def sent_requests():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [], "user_id": "user"})

    async with httpx.AsyncClient(
        base_url="https://auth.example",
        transport=httpx.MockTransport(handle),
        follow_redirects=True,
    ) as client:
        with patch(
            "src.utils.http_request_handler.get_async_client", return_value=client
        ):
            yield requests


def authn_proxy():
    return AgentexAuthenticationProxy(
        agentex_auth_url="https://auth.example", environment="production"
    )


async def call_authz(proxy, operation):
    principal = {"user_id": "user"}
    resource = AgentexResource.task("task")
    if operation == "search":
        return await proxy.list_resources(principal, AgentexResourceType.task)
    if operation in ("register", "deregister"):
        return await getattr(proxy, f"{operation}_resource")(principal, resource)
    return await getattr(proxy, operation)(
        principal, resource, AuthorizedOperationType.read
    )


@pytest.mark.asyncio
async def test_authn_uses_pod_token_and_preserves_user_credentials(
    token_path, sent_requests
):
    token_path.write_text("pod-token\n")
    headers = {
        "authorization": "Bearer user-token",
        "X-Kubernetes-Service-Account-Token": "forged-token",
        "x-KUBERNETES-service-ACCOUNT-token": "another-forged-token",
    }
    original_headers = headers.copy()

    await authn_proxy().verify_headers(headers)

    assert headers == original_headers
    request = sent_requests[0]
    assert request.url == "https://auth.example/v1/authn"
    assert request.headers.get_list(SERVICE_ACCOUNT_TOKEN_HEADER) == ["pod-token"]
    assert request.headers["authorization"] == "Bearer user-token"


@pytest.mark.parametrize(
    "operation", ["grant", "revoke", "check", "search", "register", "deregister"]
)
@pytest.mark.asyncio
async def test_all_authz_endpoints_send_the_pod_token(
    operation, token_path, sent_requests
):
    token_path.write_text("pod-token")
    proxy = AgentexAuthorizationProxy(agentex_auth_url="https://auth.example")

    await call_authz(proxy, operation)

    request = sent_requests[0]
    assert request.url == f"https://auth.example/v1/authz/{operation}"
    assert request.headers[SERVICE_ACCOUNT_TOKEN_HEADER] == "pod-token"
    assert json.loads(request.content)["principal"] == {"user_id": "user"}


@pytest.mark.parametrize("proxy_type", ["authn", "authz"])
@pytest.mark.asyncio
async def test_rotation_is_picked_up_without_recreating_proxy(
    proxy_type, token_path, sent_requests
):
    proxy = (
        authn_proxy()
        if proxy_type == "authn"
        else AgentexAuthorizationProxy(agentex_auth_url="https://auth.example")
    )
    for token in ("old-token", "rotated-token"):
        replacement = token_path.with_suffix(".new")
        replacement.write_text(token)
        replacement.replace(token_path)
        if proxy_type == "authn":
            await proxy.verify_headers({"authorization": "Bearer user-token"})
        else:
            await call_authz(proxy, "check")

    assert [
        request.headers[SERVICE_ACCOUNT_TOKEN_HEADER] for request in sent_requests
    ] == [
        "old-token",
        "rotated-token",
    ]


@pytest.mark.parametrize("contents", [None, "", " \n\t"])
@pytest.mark.parametrize("proxy_type", ["authn", "authz"])
@pytest.mark.asyncio
async def test_missing_or_empty_token_omits_header(
    contents, proxy_type, token_path, sent_requests
):
    if contents is not None:
        token_path.write_text(contents)
    if proxy_type == "authn":
        await authn_proxy().verify_headers(
            {"x-kubernetes-service-account-token": "forged-token"}
        )
    else:
        await call_authz(
            AgentexAuthorizationProxy(agentex_auth_url="https://auth.example"), "check"
        )

    assert SERVICE_ACCOUNT_TOKEN_HEADER not in sent_requests[0].headers


def test_default_path_is_used_when_override_is_unset(token_path, monkeypatch):
    token_path.write_text("default-mounted-token")
    monkeypatch.delenv("AGENTEX_AUTH_SA_TOKEN_PATH")
    monkeypatch.setattr(
        "src.adapters.authentication.service_account_token.DEFAULT_TOKEN_PATH",
        str(token_path),
    )

    assert (
        agentex_auth_headers()[SERVICE_ACCOUNT_TOKEN_HEADER] == "default-mounted-token"
    )


@pytest.mark.parametrize("failure", ["permission", "invalid_encoding"])
@pytest.mark.asyncio
async def test_unreadable_token_fails_without_exposing_secrets(
    failure, token_path, sent_requests
):
    token_path.write_bytes(b"\xffsecret-token")
    with (
        patch.object(
            Path,
            "read_text",
            side_effect=PermissionError(f"private token mount: {token_path}"),
        )
        if failure == "permission"
        else nullcontext()
    ):
        with pytest.raises(AuthenticationServiceUnavailableError) as exc:
            await authn_proxy().verify_headers({})

    assert exc.value.code == 503
    assert str(token_path) not in str(exc.value)
    assert "secret-token" not in str(exc.value)
    assert exc.value.detail is None
    assert exc.value.__suppress_context__
    assert not sent_requests


@pytest.mark.parametrize(
    "contents",
    ["secret\r\nheader", "secret header", "secret\x00header", "secretéheader"],
)
@pytest.mark.asyncio
async def test_malformed_token_cannot_leak_through_http_errors(
    contents, token_path, sent_requests
):
    token_path.write_text(contents)

    with pytest.raises(AuthenticationServiceUnavailableError) as exc:
        await authn_proxy().verify_headers({})

    assert exc.value.code == 503
    assert contents not in str(exc.value)
    assert str(token_path) not in str(exc.value)
    assert exc.value.detail is None
    assert not sent_requests


@pytest.mark.asyncio
async def test_generic_http_handler_does_not_attach_token(token_path):
    token_path.write_text("pod-token")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(
        base_url="https://other.example", transport=httpx.MockTransport(handle)
    ) as client:
        with patch(
            "src.utils.http_request_handler.get_async_client", return_value=client
        ):
            await HttpRequestHandler.post_with_error_handling(
                "https://other.example", "/endpoint"
            )

    assert requests[0].url == "https://other.example/endpoint"
    assert SERVICE_ACCOUNT_TOKEN_HEADER not in requests[0].headers


@pytest.mark.parametrize("proxy_type", ["authn", "authz"])
@pytest.mark.asyncio
async def test_provider_redirect_cannot_forward_credentials(proxy_type, token_path):
    token_path.write_text("pod-token")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            307, headers={"location": "https://other.example/collect"}
        )

    async with httpx.AsyncClient(
        base_url="https://auth.example",
        transport=httpx.MockTransport(handle),
        follow_redirects=True,
    ) as client:
        with patch(
            "src.utils.http_request_handler.get_async_client", return_value=client
        ):
            with pytest.raises(ServiceError) as exc:
                if proxy_type == "authn":
                    await authn_proxy().verify_headers({})
                else:
                    await call_authz(
                        AgentexAuthorizationProxy(
                            agentex_auth_url="https://auth.example"
                        ),
                        "check",
                    )

    assert exc.value.code == 307
    assert len(requests) == 1
    assert requests[0].url.host == "auth.example"
