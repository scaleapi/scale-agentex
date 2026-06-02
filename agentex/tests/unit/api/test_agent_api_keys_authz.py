"""AGX1-263 — agent_api_keys route migration to Spark AuthZ.

Asserts the route layer issues correct ``check`` calls and collapses denials
to 404. Two-factor SpiceDB expansion is owned by spark-authz; not tested here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.utils.agent_api_key_authorization import _check_api_key_or_collapse_to_404
from src.utils.authorization_shortcuts import DAuthorizedId


def _dep_callable(annotation):
    """Pull the inner FastAPI dependency function out of an ``Annotated[str, Depends(...)]``."""
    return annotation.__metadata__[0].dependency


@pytest.mark.unit
@pytest.mark.asyncio
class TestCheckApiKeyOrCollapseTo404:
    """Helper collapses every denial to 404 (no cross-tenant existence leak)."""

    async def test_allowed_check_returns_normally(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_api_key_or_collapse_to_404(
            authorization,
            "api-key-1",
            AuthorizedOperationType.read,
        )

        authorization.check.assert_awaited_once()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.api_key("api-key-1")
        assert called_kwargs["operation"] == AuthorizedOperationType.read

    async def test_denied_collapses_to_not_found_regardless_of_existence(self):
        """Denial surfaces as 404 regardless of existence."""
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await _check_api_key_or_collapse_to_404(
                authorization,
                "api-key-1",
                AuthorizedOperationType.delete,
            )

    async def test_uses_delete_operation_on_delete_routes(self):
        """Helper forwards the operation verbatim."""
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_api_key_or_collapse_to_404(
            authorization,
            "api-key-2",
            AuthorizedOperationType.delete,
        )

        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["operation"] == AuthorizedOperationType.delete


@pytest.mark.unit
@pytest.mark.asyncio
class TestDAuthorizedIdApiKeyWrap:
    """``DAuthorizedId(api_key, ...)`` routes through the collapse wrap → 404 on denial."""

    async def test_api_key_id_routes_through_wrap_on_denial(self):
        annotation = DAuthorizedId(
            AgentexResourceType.api_key,
            AuthorizedOperationType.read,
            param_name="id",
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        event_repository = MagicMock()
        state_repository = MagicMock()

        message_repository = MagicMock()
        with pytest.raises(ItemDoesNotExist):
            await dep(
                authorization,
                event_repository,
                state_repository,
                message_repository,
                "api-key-7",
            )

    async def test_api_key_id_returns_resource_id_when_allowed(self):
        annotation = DAuthorizedId(
            AgentexResourceType.api_key,
            AuthorizedOperationType.read,
            param_name="id",
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        result = await dep(
            authorization, MagicMock(), MagicMock(), MagicMock(), "api-key-9"
        )

        assert result == "api-key-9"
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.api_key("api-key-9")

    async def test_api_key_delete_op_propagated_to_check(self):
        """Delete op is forwarded to ``authorization.check``."""
        annotation = DAuthorizedId(
            AgentexResourceType.api_key,
            AuthorizedOperationType.delete,
            param_name="id",
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await dep(authorization, MagicMock(), MagicMock(), MagicMock(), "api-key-del")

        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["operation"] == AuthorizedOperationType.delete


@pytest.mark.unit
@pytest.mark.asyncio
class TestNameRouteCollapse:
    """Name-route handlers call the collapse helper inline → 404 on denial."""

    async def test_get_by_name_handler_collapses_denial_to_404(self):
        from src.api.routes.agent_api_keys import get_agent_api_key_by_name

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        api_key_use_case = MagicMock()
        api_key_use_case.get_by_agent_id_and_name = AsyncMock(
            return_value=MagicMock(id="api-key-named", name="prod-key")
        )
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await get_agent_api_key_by_name(
                name="prod-key",
                agent_api_key_use_case=api_key_use_case,
                agent_use_case=agent_use_case,
                authorization_service=authorization,
                agent_id="agent-1",
                agent_name=None,
            )

        # The lookup happens BEFORE the authz check — name → id is resolved,
        # then the wrap intercepts the denial.
        api_key_use_case.get_by_agent_id_and_name.assert_awaited_once()
        authorization.check.assert_awaited_once()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.api_key("api-key-named")

    async def test_delete_by_name_handler_collapses_denial_to_404(self):
        from src.api.routes.agent_api_keys import delete_agent_api_key_by_name

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        api_key_use_case = MagicMock()
        api_key_use_case.get_by_agent_id_and_name = AsyncMock(
            return_value=MagicMock(id="api-key-named")
        )
        api_key_use_case.delete_by_agent_id_and_key_name = AsyncMock()
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        authorization.principal_context = MagicMock(account_id="acct-1")

        with pytest.raises(ItemDoesNotExist):
            await delete_agent_api_key_by_name(
                api_key_name="prod-key",
                agent_api_key_use_case=api_key_use_case,
                agent_use_case=agent_use_case,
                authorization_service=authorization,
                agent_id="agent-1",
                agent_name=None,
            )

        # Crucially: the delete is NOT invoked when the check fails.
        api_key_use_case.delete_by_agent_id_and_key_name.assert_not_called()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["operation"] == AuthorizedOperationType.delete

    async def test_absent_and_denied_404_bodies_are_identical(self):
        """Absent-row and denied-row 404 bodies must be byte-for-byte identical."""
        from src.api.routes.agent_api_keys import get_agent_api_key_by_name
        from src.utils.agent_api_key_authorization import API_KEY_NOT_FOUND_MESSAGE

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))

        # Path A: row absent.
        absent_use_case = MagicMock()
        absent_use_case.get_by_agent_id_and_name = AsyncMock(return_value=None)
        with pytest.raises(ItemDoesNotExist) as absent_exc:
            await get_agent_api_key_by_name(
                name="prod-key",
                agent_api_key_use_case=absent_use_case,
                agent_use_case=agent_use_case,
                authorization_service=MagicMock(),
                agent_id="agent-1",
                agent_name=None,
            )

        # Path B: row present, authz denied.
        denied_use_case = MagicMock()
        denied_use_case.get_by_agent_id_and_name = AsyncMock(
            return_value=MagicMock(id="api-key-named")
        )
        denied_authz = MagicMock()
        denied_authz.check = AsyncMock(side_effect=AuthorizationError("denied"))
        with pytest.raises(ItemDoesNotExist) as denied_exc:
            await get_agent_api_key_by_name(
                name="prod-key",
                agent_api_key_use_case=denied_use_case,
                agent_use_case=agent_use_case,
                authorization_service=denied_authz,
                agent_id="agent-1",
                agent_name=None,
            )

        assert (
            str(absent_exc.value) == str(denied_exc.value) == API_KEY_NOT_FOUND_MESSAGE
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestListFiltering:
    """List filters to api_keys the caller has ``read`` on."""

    async def test_authorized_ids_pushed_into_use_case(self):
        """Route forwards ``authorized_api_key_ids`` as ``id=`` so the repo
        filters at the SQL layer (correct pagination)."""
        from src.api.routes.agent_api_keys import list_agent_api_keys

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        api_key_use_case = MagicMock()
        api_key_use_case.list = AsyncMock(return_value=[])

        await list_agent_api_keys(
            agent_api_key_use_case=api_key_use_case,
            agent_use_case=agent_use_case,
            authorized_api_key_ids=["api-key-a", "api-key-c"],
            agent_id="agent-1",
            agent_name=None,
            limit=50,
            page_number=1,
        )

        api_key_use_case.list.assert_awaited_once_with(
            agent_id="agent-1",
            limit=50,
            page_number=1,
            id=["api-key-a", "api-key-c"],
        )

    async def test_none_authorized_ids_passes_through(self):
        """``None`` (bypass) must pass through as ``id=None`` (no filter)."""
        from src.api.routes.agent_api_keys import list_agent_api_keys

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        api_key_use_case = MagicMock()
        api_key_use_case.list = AsyncMock(return_value=[])

        await list_agent_api_keys(
            agent_api_key_use_case=api_key_use_case,
            agent_use_case=agent_use_case,
            authorized_api_key_ids=None,
            agent_id="agent-1",
            agent_name=None,
            limit=50,
            page_number=1,
        )

        api_key_use_case.list.assert_awaited_once_with(
            agent_id="agent-1",
            limit=50,
            page_number=1,
            id=None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateParentAgentCheck:
    """``create_api_key`` gates on parent ``agent.update`` (no api_key row yet)."""

    async def test_create_checks_parent_agent_update(self):
        from src.api.routes.agent_api_keys import create_api_key
        from src.api.schemas.agent_api_keys import CreateAPIKeyRequest
        from src.domain.entities.agent_api_keys import AgentAPIKeyType

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        api_key_use_case = MagicMock()
        api_key_use_case.get_by_agent_id_and_name = AsyncMock(return_value=None)
        from datetime import datetime

        created_entity = MagicMock()
        created_entity.id = "new-api-key"
        created_entity.agent_id = "agent-1"
        created_entity.created_at = datetime(2026, 1, 1)
        created_entity.name = "prod-key"
        created_entity.api_key_type = AgentAPIKeyType.EXTERNAL
        api_key_use_case.create = AsyncMock(return_value=created_entity)
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        authorization.principal_context = MagicMock(account_id="acct-1")

        request = CreateAPIKeyRequest(
            agent_id="agent-1",
            agent_name=None,
            name="prod-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="secret-key-value",
        )

        await create_api_key(
            request=request,
            agent_api_key_use_case=api_key_use_case,
            agent_use_case=agent_use_case,
            authorization_service=authorization,
        )

        authorization.check.assert_awaited_once()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-1")
        assert called_kwargs["operation"] == AuthorizedOperationType.update

    async def test_create_denied_on_parent_agent_propagates_403(self):
        """Create denial surfaces as 403 — no api_key exists yet, no leak possible."""
        from src.api.routes.agent_api_keys import create_api_key
        from src.api.schemas.agent_api_keys import CreateAPIKeyRequest
        from src.domain.entities.agent_api_keys import AgentAPIKeyType

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        api_key_use_case = MagicMock()
        api_key_use_case.create = AsyncMock()
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        request = CreateAPIKeyRequest(
            agent_id="agent-1",
            agent_name=None,
            name="prod-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="x",
        )

        with pytest.raises(AuthorizationError):
            await create_api_key(
                request=request,
                agent_api_key_use_case=api_key_use_case,
                agent_use_case=agent_use_case,
                authorization_service=authorization,
            )
        # Create is NOT invoked when parent check fails.
        api_key_use_case.create.assert_not_called()
