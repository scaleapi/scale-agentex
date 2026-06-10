import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authorization_service_logs_do_not_serialize_principal(caplog):
    secret = "secret-api-key-value"
    request = SimpleNamespace(
        state=SimpleNamespace(
            principal_context={
                "user_id": "user-1",
                "account_id": "acct-1",
                "api_key": secret,
            },
            agent_identity=None,
        )
    )
    gateway = MagicMock()
    gateway.grant = AsyncMock()
    gateway.revoke = AsyncMock()
    gateway.check = AsyncMock(return_value=True)
    gateway.list_resources = AsyncMock(return_value=[])
    gateway.register_resource = AsyncMock()
    gateway.deregister_resource = AsyncMock()
    service = AuthorizationService(enabled=True, gateway=gateway, request=request)

    with caplog.at_level(logging.INFO):
        await service.grant(AgentexResource.agent("agent-1"))
        await service.revoke(AgentexResource.agent("agent-1"))
        await service.check(
            AgentexResource.agent("agent-1"), AuthorizedOperationType.read
        )
        await service.list_resources(AgentexResourceType.agent)
        await service.register_resource(AgentexResource.agent("agent-1"))
        await service.deregister_resource(AgentexResource.agent("agent-1"))

    assert secret not in caplog.text
    assert "principal" not in caplog.text
