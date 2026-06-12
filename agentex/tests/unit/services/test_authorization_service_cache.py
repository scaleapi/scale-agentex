from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.api.schemas.authorization_types import AgentexResource, AuthorizedOperationType
from src.domain.services.authorization_service import AuthorizationService


def _request_with_principal(principal_context):
    return SimpleNamespace(
        state=SimpleNamespace(
            principal_context=principal_context,
            agent_identity=None,
        )
    )


def _service(principal_context, gateway):
    return AuthorizationService(
        enabled=True,
        gateway=gateway,
        request=_request_with_principal(principal_context),
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource",
    [
        AgentexResource.agent("agent-1"),
        AgentexResource.task("task-1"),
        AgentexResource.api_key("api-key-1"),
        AgentexResource.schedule("agent-1/schedule-1"),
    ],
)
async def test_authorization_checks_call_gateway_each_time(resource):
    gateway = AsyncMock()
    gateway.check.return_value = True
    service = _service({"user_id": "user-1", "account_id": "acct-1"}, gateway)

    assert await service.check(resource, AuthorizedOperationType.read) is True
    assert await service.check(resource, AuthorizedOperationType.read) is True

    assert gateway.check.await_count == 2
