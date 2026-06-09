from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.adapters.authorization.adapter_agentex_authz_proxy import (
    _principal_context_payload,
)
from src.api.middleware_utils import verify_auth_gateway
from src.api.schemas.principal_context import AgentexAuthPrincipalContext


@pytest.mark.unit
def test_principal_context_model_removes_api_key_from_base_object():
    principal_context = {
        "user_id": "user-1",
        "account_id": "acct-1",
        "api_key": "secret",
        "workspace_id": "workspace-1",
    }

    principal = AgentexAuthPrincipalContext.model_validate(principal_context)

    assert not hasattr(principal, "api_key")
    assert principal.model_dump(exclude_none=True) == {
        "user_id": "user-1",
        "account_id": "acct-1",
        "workspace_id": "workspace-1",
    }


@pytest.mark.unit
def test_principal_context_model_removes_api_key_name_variants():
    principal = AgentexAuthPrincipalContext.model_validate(
        {
            "user_id": "user-1",
            "apiKey": "secret-1",
            "api-key": "secret-2",
        }
    )

    assert principal.model_dump(exclude_none=True) == {"user_id": "user-1"}


@pytest.mark.unit
def test_principal_context_payload_serializes_without_api_key():
    payload = _principal_context_payload(
        {
            "user_id": "user-1",
            "account_id": "acct-1",
            "api_key": "secret-key",
        }
    )

    assert payload == {
        "user_id": "user-1",
        "account_id": "acct-1",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_auth_gateway_stores_sanitized_principal_context():
    request = SimpleNamespace(
        headers={"x-api-key": "secret-key"},
        state=SimpleNamespace(),
        method="GET",
        url=SimpleNamespace(path="/agents"),
    )
    auth_gateway = SimpleNamespace(
        verify_headers=AsyncMock(
            return_value={
                "user_id": "user-1",
                "account_id": "acct-1",
                "api_key": "secret-key",
            }
        )
    )

    response = await verify_auth_gateway(request, auth_gateway)

    assert response is None
    assert isinstance(request.state.principal_context, AgentexAuthPrincipalContext)
    assert request.state.principal_context.model_dump(exclude_none=True) == {
        "user_id": "user-1",
        "account_id": "acct-1",
    }
