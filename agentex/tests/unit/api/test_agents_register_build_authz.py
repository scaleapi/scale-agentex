"""Route-level authz tests for agent build registration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.api.routes.agents import register_build
from src.api.schemas.agents import RegisterBuildRequest
from src.api.schemas.authorization_types import AgentexResource, AuthorizedOperationType
from src.domain.entities.agents import AgentEntity, AgentStatus


def _agent() -> AgentEntity:
    now = datetime.now(tz=UTC)
    return AgentEntity(
        id="agent-123",
        name="build-agent",
        description="Created from build",
        status=AgentStatus.BUILD_ONLY,
        status_reason="Agent build registered; not yet deployed.",
        acp_url=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_build_registers_agent_resource() -> None:
    """Build-time agent creation must call register_resource, not grant-only."""
    agents_use_case = MagicMock()
    agents_use_case.register_build = AsyncMock(return_value=_agent())
    authorization_service = MagicMock()
    authorization_service.check = AsyncMock(return_value=True)
    authorization_service.register_resource = AsyncMock(return_value=None)
    authorization_service.grant = AsyncMock(return_value=None)
    principal_context = {
        "account_id": "account-123",
        "user_id": "user-123",
        "api_key": "test-key",
    }

    result = await register_build(
        request=RegisterBuildRequest(
            name="build-agent",
            description="Created from build",
            principal_context=principal_context,
        ),
        agents_use_case=agents_use_case,
        authorization_service=authorization_service,
    )

    assert result.id == "agent-123"
    authorization_service.check.assert_awaited_once_with(
        AgentexResource.agent("*"),
        AuthorizedOperationType.create,
        principal_context=principal_context,
    )
    agents_use_case.register_build.assert_awaited_once_with(
        name="build-agent",
        description="Created from build",
        registration_metadata=None,
        agent_input_type=None,
    )
    authorization_service.register_resource.assert_awaited_once_with(
        AgentexResource.agent("agent-123"),
        principal_context=principal_context,
    )
    authorization_service.grant.assert_not_awaited()
