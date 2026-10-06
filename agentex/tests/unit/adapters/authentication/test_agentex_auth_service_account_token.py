import asyncio
import json
import threading
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from src.adapters.authentication import service_account_token
from src.adapters.authentication.adapter_agentex_authn_proxy import (
    AgentexAuthenticationProxy,
)
from src.adapters.authentication.exceptions import (
    AuthenticationError,
    AuthenticationGatewayError,
    AuthenticationServiceUnavailableError,
)
from src.adapters.authentication.service_account_token import (
    SERVICE_ACCOUNT_TOKEN_HEADER,
    agentex_auth_headers,
)
from src.adapters.authorization.adapter_agentex_authz_proxy import (
    AgentexAuthorizationProxy,
)
from src.adapters.authorization.exceptions import AuthorizationError
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.exceptions import ServiceError
from src.utils.http_request_handler import HttpRequestHandler, _redact

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


@pytest.mark.asyncio
async def test_default_path_is_used_when_override_is_unset(token_path, monkeypatch):
    token_path.write_text("default-mounted-token")
    monkeypatch.delenv("AGENTEX_AUTH_SA_TOKEN_PATH")
    monkeypatch.setattr(
        "src.adapters.authentication.service_account_token.DEFAULT_TOKEN_PATH",
        str(token_path),
    )

    assert (await agentex_auth_headers())[
        SERVICE_ACCOUNT_TOKEN_HEADER
    ] == "default-mounted-token"


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


@pytest.mark.parametrize("proxy_type", ["authn", "authz"])
@pytest.mark.asyncio
async def test_slow_token_read_leaves_event_loop_responsive(
    proxy_type, monkeypatch, token_path, sent_requests
):
    loop = asyncio.get_running_loop()
    read_started = asyncio.Event()
    release_read = threading.Event()

    def read_token(*args, **kwargs):
        loop.call_soon_threadsafe(read_started.set)
        # Finite wait also lets the test fail instead of hanging if IO regresses
        # to running on the event loop.
        if not release_read.wait(timeout=2):
            raise TimeoutError("token read was not released")
        return "pod-token"

    monkeypatch.setattr(Path, "read_text", read_token)
    request = asyncio.create_task(
        authn_proxy().verify_headers({})
        if proxy_type == "authn"
        else call_authz(
            AgentexAuthorizationProxy(agentex_auth_url="https://auth.example"), "check"
        )
    )
    try:
        await asyncio.wait_for(read_started.wait(), timeout=1)
        # This coroutine must resume while the filesystem read is still blocked.
        assert not request.done()
        assert not sent_requests
    finally:
        release_read.set()
        await request

    assert sent_requests[0].headers[SERVICE_ACCOUNT_TOKEN_HEADER] == "pod-token"


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
            with pytest.raises(AuthenticationGatewayError) as exc:
                if proxy_type == "authn":
                    await authn_proxy().verify_headers({})
                else:
                    await call_authz(
                        AgentexAuthorizationProxy(
                            agentex_auth_url="https://auth.example"
                        ),
                        "check",
                    )

    assert exc.value.code == 502
    assert "redirect status 307" in exc.value.message
    assert "/v1/auth" in exc.value.message
    assert "other.example" not in exc.value.message
    assert len(requests) == 1
    assert requests[0].url.host == "auth.example"


@pytest.fixture
def provider_response():
    response = {"status": 200, "headers": {}, "json": {}}
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            response["status"], headers=response["headers"], json=response["json"]
        )

    return response, requests, handle


async def call_provider(proxy_type, handle):
    async with httpx.AsyncClient(
        base_url="https://auth.example", transport=httpx.MockTransport(handle)
    ) as client:
        with patch(
            "src.utils.http_request_handler.get_async_client", return_value=client
        ):
            if proxy_type == "authn":
                return await authn_proxy().verify_headers(
                    {"authorization": "Bearer user-secret-credential"}
                )
            return await call_authz(
                AgentexAuthorizationProxy(agentex_auth_url="https://auth.example"),
                "check",
            )


@pytest.mark.parametrize("reason", ["unauthenticated", "forbidden", "unavailable"])
@pytest.mark.parametrize("status", [401, 403, 503])
@pytest.mark.parametrize("proxy_type", ["authn", "authz"])
@pytest.mark.asyncio
async def test_service_account_rejection_is_a_service_error(
    proxy_type, status, reason, token_path, provider_response, caplog
):
    token_path.write_text("pod-token")
    response, _, handle = provider_response
    response.update(
        status=status,
        headers={"X-Service-Account-Auth-Error": reason},
        json={"detail": "caller rejected"},
    )

    with pytest.raises(AuthenticationServiceUnavailableError) as exc:
        await call_provider(proxy_type, handle)

    assert exc.value.code == 503
    assert reason in exc.value.message
    assert f"X-Service-Account-Auth-Error={reason} (status {status})" in caplog.text
    assert any(record.levelname == "ERROR" for record in caplog.records)


@pytest.mark.asyncio
async def test_unrecognized_service_account_reason_is_not_echoed(
    token_path, provider_response, caplog
):
    token_path.write_text("pod-token")
    response, _, handle = provider_response
    response.update(status=401, headers={"X-Service-Account-Auth-Error": "injected"})

    with pytest.raises(AuthenticationServiceUnavailableError) as exc:
        await call_provider("authn", handle)

    assert "unrecognized" in exc.value.message
    assert "injected" not in caplog.text


@pytest.mark.parametrize(
    ("status", "expected"), [(401, AuthenticationError), (403, AuthorizationError)]
)
@pytest.mark.asyncio
async def test_user_rejection_without_service_account_header_stays_client_error(
    status, expected, token_path, provider_response
):
    token_path.write_text("pod-token")
    response, _, handle = provider_response
    response.update(status=status, json={"detail": "user rejected"})

    with pytest.raises(expected) as exc:
        await call_provider("authz", handle)

    assert exc.value.message == "user rejected"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@pytest.mark.parametrize("proxy_type", ["authn", "authz"])
@pytest.mark.asyncio
async def test_provider_5xx_is_service_unavailable(
    proxy_type, status, token_path, provider_response
):
    token_path.write_text("pod-token")
    response, _, handle = provider_response
    response.update(status=status, json={"detail": "upstream down"})

    with pytest.raises(AuthenticationServiceUnavailableError) as exc:
        await call_provider(proxy_type, handle)

    assert exc.value.code == 503
    assert exc.value.detail == "upstream down"


@pytest.mark.asyncio
async def test_provider_errors_redact_echoed_credentials(token_path, provider_response):
    token_path.write_text("pod-token-value")
    response, _, handle = provider_response
    response.update(
        status=403, json={"detail": "bad user-secret-credential pod-token-value"}
    )

    with pytest.raises(AuthorizationError) as exc:
        await call_provider("authn", handle)

    assert "user-secret-credential" not in exc.value.message
    assert "pod-token-value" not in exc.value.message
    assert exc.value.message == "bad [REDACTED] [REDACTED]"


@pytest.mark.asyncio
async def test_truncated_plain_text_error_cannot_leak_credential_prefix(token_path):
    pod_token = "a" * 300
    token_path.write_text(pod_token)

    def handle(request):
        return httpx.Response(500, text="invalid token " + pod_token)

    with pytest.raises(AuthenticationServiceUnavailableError) as exc:
        await call_provider("authz", handle)

    assert exc.value.detail == "invalid token [REDACTED]"
    assert "aa" not in exc.value.detail


@pytest.mark.asyncio
async def test_short_echoed_credentials_are_redacted():
    def handle(request):
        return httpx.Response(401, json={"detail": "bad abc"})

    async with httpx.AsyncClient(
        base_url="https://auth.example", transport=httpx.MockTransport(handle)
    ) as client:
        with patch(
            "src.utils.http_request_handler.get_async_client", return_value=client
        ):
            with pytest.raises(AuthenticationError) as exc:
                await authn_proxy().verify_headers({"authorization": "Bearer abc"})

    assert "abc" not in exc.value.message
    assert exc.value.message == "bad [REDACTED]"


def test_redaction_is_single_pass_and_keeps_cookie_names():
    assert _redact("x abc y", ["abc", "RED"]) == "x [REDACTED] y"
    assert (
        _redact("session ok, value 9z", ["session=9z"])
        == "session ok, value [REDACTED]"
    )
    assert _redact("tok abc== abc", ["abc=="]) == "tok [REDACTED] [REDACTED]"


@pytest.mark.asyncio
async def test_non_credential_headers_are_not_redacted():
    def handle(request):
        return httpx.Response(400, json={"detail": "expected application/json"})

    async with httpx.AsyncClient(
        base_url="https://auth.example", transport=httpx.MockTransport(handle)
    ) as client:
        with patch(
            "src.utils.http_request_handler.get_async_client", return_value=client
        ):
            with pytest.raises(ServiceError) as exc:
                await HttpRequestHandler.post_with_error_handling(
                    "https://auth.example",
                    "/v1/authn",
                    headers={"Content-Type": "application/json"},
                )

    assert exc.value.detail == "expected application/json"


@pytest.mark.asyncio
async def test_missing_token_file_warns_once_with_path(
    token_path, sent_requests, monkeypatch, caplog
):
    monkeypatch.setattr(service_account_token, "_missing_token_paths_warned", set())

    await agentex_auth_headers()
    await agentex_auth_headers()

    warnings = [r for r in caplog.records if str(token_path) in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelname == "WARNING"
