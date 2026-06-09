"""Agent direct-route authorization: denied reads/deletes collapse to 404.

Asserts the route layer issues the right ``check`` calls and collapses a denial
to 404 (so callers can't probe cross-tenant existence), and that list filtering
forwards the authorized-id set to the use case.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.routes.agents import register_agent
from src.api.schemas.agents import RegisterAgentRequest
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.utils.authorization_shortcuts import (
    DAuthorizedId,
    DAuthorizedName,
    DAuthorizedQuery,
    _check_agent_or_collapse_to_404,
)


def _dep_callable(annotation):
    """Pull the inner FastAPI dependency function out of an ``Annotated[str, Depends(...)]``."""
    return annotation.__metadata__[0].dependency


@pytest.mark.unit
@pytest.mark.asyncio
class TestCheckAgentOrCollapseTo404:
    """Helper collapses every denial to 404 (no cross-tenant existence leak)."""

    async def test_allowed_check_returns_normally(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_agent_or_collapse_to_404(
            authorization,
            "agent-1",
            AuthorizedOperationType.read,
        )

        authorization.check.assert_awaited_once()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-1")
        assert called_kwargs["operation"] == AuthorizedOperationType.read

    async def test_denied_collapses_to_not_found(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await _check_agent_or_collapse_to_404(
                authorization,
                "agent-1",
                AuthorizedOperationType.delete,
            )

    async def test_operation_forwarded_verbatim(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_agent_or_collapse_to_404(
            authorization,
            "agent-2",
            AuthorizedOperationType.delete,
        )

        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["operation"] == AuthorizedOperationType.delete


@pytest.mark.unit
@pytest.mark.asyncio
class TestDAuthorizedIdAgentWrap:
    """``DAuthorizedId(agent, ...)`` routes through the collapse wrap → 404 on denial."""

    async def test_agent_id_returns_resource_id_when_allowed(self):
        annotation = DAuthorizedId(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        result = await dep(
            authorization, MagicMock(), MagicMock(), MagicMock(), "agent-9"
        )

        assert result == "agent-9"
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-9")
        assert called_kwargs["operation"] == AuthorizedOperationType.read

    async def test_agent_id_routes_through_wrap_on_denial(self):
        annotation = DAuthorizedId(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await dep(authorization, MagicMock(), MagicMock(), MagicMock(), "agent-7")

    async def test_agent_delete_op_propagated_to_check(self):
        annotation = DAuthorizedId(
            AgentexResourceType.agent, AuthorizedOperationType.delete
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await dep(authorization, MagicMock(), MagicMock(), MagicMock(), "agent-del")

        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["operation"] == AuthorizedOperationType.delete


@pytest.mark.unit
@pytest.mark.asyncio
class TestDAuthorizedNameAgentWrap:
    """``DAuthorizedName(agent, ...)``: lookup-then-collapse on the resolved id."""

    async def test_present_but_denied_collapses_to_404(self):
        annotation = DAuthorizedName(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        agent_repository = MagicMock()
        agent_repository.get = AsyncMock(return_value=MagicMock(id="agent-resolved"))
        task_repository = MagicMock()
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await dep(authorization, agent_repository, task_repository, "prod-agent")

        # Name was resolved to an id BEFORE the authz check intercepted the denial.
        agent_repository.get.assert_awaited_once_with(name="prod-agent")
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-resolved")

    async def test_absent_name_surfaces_native_404_without_checking(self):
        annotation = DAuthorizedName(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        agent_repository = MagicMock()
        agent_repository.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        task_repository = MagicMock()
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        with pytest.raises(ItemDoesNotExist):
            await dep(authorization, agent_repository, task_repository, "missing-agent")

        # Truly-absent name → repo's native 404, and no authz check is attempted.
        authorization.check.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestDAuthorizedQueryAgentWrap:
    """``DAuthorizedQuery(agent, ...)`` also collapses denied checks to 404."""

    async def test_agent_query_returns_resource_id_when_allowed(self):
        annotation = DAuthorizedQuery(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        result = await dep(
            authorization, MagicMock(), MagicMock(), MagicMock(), "agent-query"
        )

        assert result == "agent-query"
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-query")
        assert called_kwargs["operation"] == AuthorizedOperationType.read

    async def test_agent_query_routes_through_wrap_on_denial(self):
        annotation = DAuthorizedQuery(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await dep(
                authorization, MagicMock(), MagicMock(), MagicMock(), "agent-query"
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestListFiltering:
    """List forwards the authorized-id set to the use case (SQL-layer filtering)."""

    async def test_authorized_ids_pushed_into_use_case(self):
        from src.api.routes.agents import list_agents

        agents_use_case = MagicMock()
        agents_use_case.list = AsyncMock(return_value=[])

        await list_agents(
            agents_use_case=agents_use_case,
            _authorized_ids=["agent-a", "agent-c"],
            task_id=None,
            limit=50,
            page_number=1,
            order_by=None,
            order_direction="desc",
        )

        agents_use_case.list.assert_awaited_once_with(
            task_id=None,
            limit=50,
            page_number=1,
            order_by=None,
            order_direction="desc",
            id=["agent-a", "agent-c"],
        )

    async def test_none_authorized_ids_passes_through_unfiltered(self):
        from src.api.routes.agents import list_agents

        agents_use_case = MagicMock()
        agents_use_case.list = AsyncMock(return_value=[])

        await list_agents(
            agents_use_case=agents_use_case,
            _authorized_ids=None,
            task_id=None,
            limit=50,
            page_number=1,
            order_by=None,
            order_direction="desc",
        )

        # ``None`` (authz bypass / disabled) means no id filter is applied.
        agents_use_case.list.assert_awaited_once_with(
            task_id=None,
            limit=50,
            page_number=1,
            order_by=None,
            order_direction="desc",
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestRegisterAgentOwnershipEnforcement:
    """``/agents/register`` is whitelisted, so deployed pods self-register with
    no principal. The create check / ownership grant must be skipped on that
    path (the agent is already owned from build time), so a ``None`` principal
    does not 422 and crash-loop the pod. An authenticated caller is enforced."""

    @staticmethod
    def _mocks(principal_context):
        authorization = MagicMock()
        authorization.principal_context = principal_context
        authorization.check = AsyncMock(return_value=True)
        authorization.grant = AsyncMock()

        now = datetime.now(timezone.utc)
        agent = AgentEntity(
            id="agent-1",
            name="my-agent",
            description="d",
            acp_type=ACPType.ASYNC,
            status=AgentStatus.READY,
            acp_url="http://agent:5000",
            created_at=now,
            updated_at=now,
        )
        agents_use_case = MagicMock()
        agents_use_case.register_agent = AsyncMock(return_value=agent)

        api_keys_use_case = MagicMock()
        existing_key = MagicMock()
        existing_key.api_key = "internal-key"
        api_keys_use_case.get_internal_api_key_by_agent_id = AsyncMock(
            return_value=existing_key
        )
        return authorization, agents_use_case, api_keys_use_case

    @staticmethod
    def _request():
        return RegisterAgentRequest(
            name="my-agent",
            description="d",
            acp_url="http://agent:5000",
            acp_type=ACPType.ASYNC,
        )

    async def test_no_principal_skips_check_and_grant(self):
        authz, use_case, api_keys = self._mocks(principal_context=None)

        resp = await register_agent(self._request(), use_case, authz, api_keys)

        authz.check.assert_not_awaited()
        authz.grant.assert_not_awaited()
        use_case.register_agent.assert_awaited_once()
        assert resp.agent_api_key == "internal-key"

    async def test_authenticated_caller_enforces_check_and_grant(self):
        authz, use_case, api_keys = self._mocks(
            principal_context={"user_id": "u", "account_id": "acct"}
        )

        await register_agent(self._request(), use_case, authz, api_keys)

        authz.check.assert_awaited_once()
        authz.grant.assert_awaited_once()
