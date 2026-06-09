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
async def test_register_build_grants_legacy_ownership_after_create() -> None:
    """Build-time agent creation gates on authz and grants legacy ownership."""
    agents_use_case = MagicMock()
    agents_use_case.register_build = AsyncMock(return_value=_agent())
    authorization_service = MagicMock()
    authorization_service.check = AsyncMock(return_value=True)
    authorization_service.register_resource = AsyncMock(return_value=None)
    authorization_service.grant = AsyncMock(return_value=None)

    result = await register_build(
        request=RegisterBuildRequest(
            name="build-agent",
            description="Created from build",
        ),
        agents_use_case=agents_use_case,
        authorization_service=authorization_service,
    )

    assert result.id == "agent-123"
    authorization_service.check.assert_awaited_once_with(
        AgentexResource.agent("*"),
        AuthorizedOperationType.create,
    )
    agents_use_case.register_build.assert_awaited_once_with(
        name="build-agent",
        description="Created from build",
        registration_metadata=None,
        agent_input_type=None,
    )
    authorization_service.register_resource.assert_not_awaited()
    authorization_service.grant.assert_awaited_once_with(
        AgentexResource.agent("agent-123"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_build_existing_agent_path_stays_route_reentrant() -> None:
    """Idempotent-by-name path still grants legacy ownership at the route."""
    existing_agent = _agent()
    agents_use_case = MagicMock()
    agents_use_case.register_build = AsyncMock(return_value=existing_agent)
    authorization_service = MagicMock()
    authorization_service.check = AsyncMock(return_value=True)
    authorization_service.register_resource = AsyncMock(return_value=None)
    authorization_service.grant = AsyncMock(return_value=None)
    request = RegisterBuildRequest(
        name="build-agent",
        description="Created from build",
    )

    first = await register_build(
        request=request,
        agents_use_case=agents_use_case,
        authorization_service=authorization_service,
    )
    second = await register_build(
        request=request,
        agents_use_case=agents_use_case,
        authorization_service=authorization_service,
    )

    assert first.id == existing_agent.id
    assert second.id == existing_agent.id
    assert agents_use_case.register_build.await_count == 2
    assert authorization_service.check.await_count == 2
    for call in authorization_service.check.await_args_list:
        assert call.args == (
            AgentexResource.agent("*"),
            AuthorizedOperationType.create,
        )
        assert call.kwargs == {}
    authorization_service.register_resource.assert_not_awaited()
    assert authorization_service.grant.await_count == 2
    for call in authorization_service.grant.await_args_list:
        assert call.args == (AgentexResource.agent("agent-123"),)
        assert call.kwargs == {}
