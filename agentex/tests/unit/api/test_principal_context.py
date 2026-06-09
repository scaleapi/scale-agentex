from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.api.middleware_utils import verify_auth_gateway
from src.api.schemas.principal_context import remove_api_key_from_principal_context


@pytest.mark.unit
def test_remove_api_key_from_principal_context_removes_key_variants_recursively():
    principal_context = {
        "user_id": "user-1",
        "account_id": "acct-1",
        "api_key": "secret-1",
        "nested": {
            "apiKey": "secret-2",
            "items": [{"api-key": "secret-3", "safe": "kept"}],
        },
    }

    assert remove_api_key_from_principal_context(principal_context) == {
        "user_id": "user-1",
        "account_id": "acct-1",
        "nested": {"items": [{"safe": "kept"}]},
    }


@pytest.mark.unit
def test_remove_api_key_from_principal_context_preserves_object_shape():
    principal_context = SimpleNamespace(
        user_id="user-1",
        account_id="acct-1",
        api_key="secret",
    )

    sanitized = remove_api_key_from_principal_context(principal_context)

    assert sanitized.user_id == "user-1"
    assert sanitized.account_id == "acct-1"
    assert not hasattr(sanitized, "api_key")


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
    assert request.state.principal_context == {
        "user_id": "user-1",
        "account_id": "acct-1",
    }
