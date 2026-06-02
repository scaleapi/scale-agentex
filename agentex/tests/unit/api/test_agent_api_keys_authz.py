"""Tests for AGX1-263 — agent_api_keys route migration to Spark AuthZ.

Mirrors the structure of ``test_tasks_authz.py`` (AGX1-275, PR #249). Covers:

  1. The ``_check_api_key_or_collapse_to_404`` helper (allow + denied-collapses).
  2. ``DAuthorizedId`` for ``api_key`` routes the check through the collapse
     wrap so denied id-path calls return 404, not 403.
  3. The name-route handlers (``get_agent_api_key_by_name`` /
     ``delete_agent_api_key_by_name``) call the collapse helper explicitly so
     present-but-denied surfaces as 404 (the critical no-existence-leak path).
  4. ``list_agent_api_keys`` filters to the set returned by
     ``DAuthorizedResourceIds``.
  5. ``create_api_key`` enforces parent ``agent.update`` (the only route where
     no api_key resource exists yet).

Cross-tenant / two-factor-via-SpiceDB checks belong in an end-to-end suite
gated on a live spark-authz cluster (the schema's ``api_key.delete =
internal_effective_editor & parent_agent->update & internal_tenant_gate``
expansion is owned by spark-authz, not this repo). Here we only assert that
the route layer issues the correct ``check`` call with the correct operation
and surfaces denials as 404.
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
    """The api_key-resource authz wrap collapses every denial to 404 so callers
    can't distinguish "present in another tenant" from "absent" via the name or
    id routes."""

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
        """Both "denied + api_key exists" and "denied + api_key missing"
        surface as ``ItemDoesNotExist`` (→ 404). The wrap doesn't consult any
        repository — collapsing avoids the cross-tenant existence leak."""
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await _check_api_key_or_collapse_to_404(
                authorization,
                "api-key-1",
                AuthorizedOperationType.delete,
            )

    async def test_uses_delete_operation_on_delete_routes(self):
        """Sanity-check that the helper forwards the operation verbatim — the
        two-factor SpiceDB expansion for ``delete`` is what bundles in the
        ``parent_agent->update`` factor."""
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
    """``DAuthorizedId`` for ``AgentexResourceType.api_key`` must route the
    check through the collapse wrap so denied id-path calls surface as 404,
    matching the name-route behavior."""

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
        """Two-factor mutations rely on SpiceDB's transitive expansion of
        ``api_key.delete`` (which includes ``parent_agent->update``), so the
        route layer just needs to forward the ``delete`` operation correctly."""
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
    """The name-route handlers don't fit ``DAuthorizedName`` (the lookup is
    ``(agent_id, name, api_key_type)``), so they call the collapse helper
    inline. Tests verify that direct call collapses denials to 404."""

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


@pytest.mark.unit
@pytest.mark.asyncio
class TestListFiltering:
    """``list_agent_api_keys`` must filter rows to those the caller has
    ``read`` on, per the ``DAuthorizedResourceIds`` enumeration."""

    async def test_authorized_ids_pushed_into_use_case(self):
        """The route forwards ``authorized_api_key_ids`` to
        ``use_case.list(id=...)`` so the repo filters at the SQL layer.
        Pagination/limit then apply post-filter, which the old in-Python
        filter broke."""
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
        """``None`` from the authz backend = "couldn't enumerate" (e.g. bypass
        mode). Must forward ``id=None`` so the use case skips the filter."""
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
    """``create_api_key`` is the only route where no api_key resource exists
    yet, so SpiceDB cannot transitively gate on it. The route MUST explicitly
    check ``agent.update`` on the parent."""

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
        """Create-time denial bubbles out as ``AuthorizationError`` (→ 403),
        NOT collapsed to 404 — there is no api_key resource yet whose
        existence could be leaked. Mirrors agent-side denial UX."""
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
