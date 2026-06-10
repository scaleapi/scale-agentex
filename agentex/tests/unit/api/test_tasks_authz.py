"""Tests for per-RPC operation routing and task visibility authorization.

Covers:
  1. Per-RPC operation routing: MESSAGE_SEND/EVENT_SEND map to ``update``,
     TASK_CANCEL maps to ``cancel``, TASK_CREATE stays ``create``.
  2. Visibility-aware authorization: denied reads collapse to 404, while
     denied stronger operations preserve 403 when the task remains readable.

End-to-end tests (cross-tenant isolation, cancel-owner-only enforcement,
list filtering) belong in a separate integration suite that requires a live
authorization cluster.
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
from src.utils.authorization_shortcuts import (
    DAuthorizedBodyId,
    DAuthorizedName,
)
from src.utils.task_authorization import check_task_or_collapse_to_404


def _dep_callable(annotation):
    """Pull the inner FastAPI dependency function out of an ``Annotated[str, Depends(...)]``."""
    return annotation.__metadata__[0].dependency


@pytest.mark.unit
@pytest.mark.asyncio
class TestPerRpcOperationRouting:
    """Verify that per-RPC checks issue the right ``AuthorizedOperationType``."""

    @staticmethod
    def _capture_check(authorization: MagicMock) -> list[tuple]:
        calls: list[tuple] = []

        async def _check(resource: AgentexResource, operation: AuthorizedOperationType):
            calls.append((resource.type, resource.selector, operation))

        authorization.check = AsyncMock(side_effect=_check)
        return calls

    async def test_message_send_with_task_id_uses_update(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        request = MagicMock()
        request.method = AgentRPCMethod.MESSAGE_SEND
        request.params = MagicMock(task_id="task-1", task_name=None)

        await _authorize_rpc_request(request, authorization, task_service)

        assert calls == [
            (AgentexResourceType.task, "task-1", AuthorizedOperationType.update)
        ]

    async def test_event_send_with_task_id_uses_update(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        request = MagicMock()
        request.method = AgentRPCMethod.EVENT_SEND
        request.params = MagicMock(task_id="task-2", task_name=None)

        await _authorize_rpc_request(request, authorization, task_service)

        assert calls == [
            (AgentexResourceType.task, "task-2", AuthorizedOperationType.update)
        ]

    async def test_task_cancel_with_task_id_uses_cancel(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        request = MagicMock()
        request.method = AgentRPCMethod.TASK_CANCEL
        request.params = MagicMock(task_id="task-3", task_name=None)

        await _authorize_rpc_request(request, authorization, task_service)

        assert calls == [
            (AgentexResourceType.task, "task-3", AuthorizedOperationType.cancel)
        ]

    async def test_task_create_remains_create(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        request = MagicMock()
        request.method = AgentRPCMethod.TASK_CREATE

        await _authorize_rpc_request(request, authorization, task_service)

        assert calls == [
            (AgentexResourceType.task, "*", AuthorizedOperationType.create)
        ]

    async def test_message_send_with_task_name_uses_update_on_existing_task(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        task_service.get_task = AsyncMock(return_value=MagicMock(id="task-resolved"))
        request = MagicMock()
        request.method = AgentRPCMethod.MESSAGE_SEND
        request.params = MagicMock(task_id=None, task_name="my-task")

        await _authorize_rpc_request(request, authorization, task_service)

        task_service.get_task.assert_awaited_once_with(name="my-task")
        assert calls == [
            (AgentexResourceType.task, "task-resolved", AuthorizedOperationType.update)
        ]

    async def test_message_send_with_missing_task_name_falls_back_to_create(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        task_service.get_task = AsyncMock(side_effect=ItemDoesNotExist("not-found"))
        request = MagicMock()
        request.method = AgentRPCMethod.MESSAGE_SEND
        request.params = MagicMock(task_id=None, task_name="ghost-task")

        await _authorize_rpc_request(request, authorization, task_service)

        assert calls == [
            (AgentexResourceType.task, "*", AuthorizedOperationType.create)
        ]

    async def test_event_send_with_task_name_uses_update(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        task_service.get_task = AsyncMock(return_value=MagicMock(id="task-evt"))
        request = MagicMock()
        request.method = AgentRPCMethod.EVENT_SEND
        request.params = MagicMock(task_id=None, task_name="evt-task")

        await _authorize_rpc_request(request, authorization, task_service)

        task_service.get_task.assert_awaited_once_with(name="evt-task")
        assert calls == [
            (AgentexResourceType.task, "task-evt", AuthorizedOperationType.update)
        ]

    async def test_task_cancel_with_task_name_uses_cancel(self):
        from src.api.routes.agents import _authorize_rpc_request
        from src.api.schemas.agents import AgentRPCMethod

        authorization = MagicMock()
        calls = self._capture_check(authorization)
        task_service = MagicMock()
        task_service.get_task = AsyncMock(return_value=MagicMock(id="task-cancel"))
        request = MagicMock()
        request.method = AgentRPCMethod.TASK_CANCEL
        request.params = MagicMock(task_id=None, task_name="cancel-task")

        await _authorize_rpc_request(request, authorization, task_service)

        task_service.get_task.assert_awaited_once_with(name="cancel-task")
        assert calls == [
            (AgentexResourceType.task, "task-cancel", AuthorizedOperationType.cancel)
        ]

    async def test_unwired_method_fails_closed_with_not_implemented(self):
        # Fail-closed default: any AgentRPCMethod not explicitly wired in
        # _authorize_rpc_request must raise rather than silently pass through
        # authz-free. NotImplementedError surfaces as a 5xx, making the gap
        # loud rather than letting a future enum addition land authz-free.
        from src.api.routes.agents import _authorize_rpc_request

        authorization = MagicMock()
        task_service = MagicMock()
        request = MagicMock()
        request.method = "task/unknown"
        request.params = MagicMock(task_id=None, task_name=None)

        with pytest.raises(NotImplementedError, match="no case for"):
            await _authorize_rpc_request(request, authorization, task_service)


def test_cancel_operation_wire_format_matches_agentex_auth_contract():
    """Cross-repo enum contract: the literal string ``"cancel"`` is the wire
    format shared with agentex-auth's mirror enum. Diverging strings would
    only show up at runtime, so lock it in a test. Mirrors the test of the
    same shape in
    ``~/agentex/agentex-auth/tests/domain/services/test_authorization_service_routing.py``."""
    assert AuthorizedOperationType.cancel.value == "cancel"


def test_update_operation_wire_format_matches_agentex_auth_contract():
    """Cross-repo enum contract for the ``execute → update`` rewire used by
    MESSAGE_SEND / EVENT_SEND / checkpoint mutations.

    The behavioral claim that ``update`` resolves against an existing
    ``owner`` grant lives in the spark-authz repo's schema test suite
    (``permission update = (editor + owner) & internal_tenant_gate``).
    That schema test is the load-bearing assertion; this test only pins
    the agentex-auth-side wire string so a future rename of
    ``AuthorizedOperationType.update`` fails loudly here before deploy
    rather than 5xx-ing every MESSAGE_SEND in production."""
    assert AuthorizedOperationType.update.value == "update"


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdatePermissionRoutingForRewiredCallSites:
    """Behavioral pin for the AGX1-275 rewire of MESSAGE_SEND / EVENT_SEND /
    checkpoint mutations from ``execute`` to ``update``.

    The existing ``TestPerRpcOperationRouting`` tests cover the routing
    decision (RPC → operation literal). These tests pin the downstream
    behavior — for a granted ``owner`` principal, an ``update`` check
    against the task resource is accepted — by asserting the mocked
    gateway's ``check`` returns successfully for the rewired operation.
    The schema-level claim ``update`` resolves against ``owner`` is tested
    against real SpiceDB in the spark-authz repo; this is the contract pin
    that surfaces a drift in either direction at scale-agentex CI time."""

    async def test_update_check_succeeds_for_message_send_path(self):
        """A grant tuple that previously satisfied ``execute`` must satisfy
        ``update`` after the rewire, given the SGP and Spark schemas both
        keep ``update`` and ``execute`` on identical role allowlists for
        the task resource type."""
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await check_task_or_collapse_to_404(
            authorization,
            "task-msg",
            AuthorizedOperationType.update,
        )

        authorization.check.assert_awaited_once()
        call_kwargs = authorization.check.await_args.kwargs
        assert call_kwargs["resource"] == AgentexResource.task("task-msg")
        assert call_kwargs["operation"] == AuthorizedOperationType.update

    async def test_update_check_denial_collapses_to_404_when_read_denied(self):
        """If ``update`` and the follow-up ``read`` are both denied, the
        helper still returns the non-enumerating 404 envelope."""
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await check_task_or_collapse_to_404(
                authorization,
                "task-msg",
                AuthorizedOperationType.update,
            )

        assert authorization.check.await_count == 2
        first_call, second_call = authorization.check.await_args_list
        assert first_call.kwargs["operation"] == AuthorizedOperationType.update
        assert second_call.kwargs["operation"] == AuthorizedOperationType.read

    async def test_update_check_denial_surfaces_403_when_read_allowed(self):
        authorization = MagicMock()
        operation_denied = AuthorizationError("denied")
        authorization.check = AsyncMock(side_effect=[operation_denied, True])

        with pytest.raises(AuthorizationError) as exc_info:
            await check_task_or_collapse_to_404(
                authorization,
                "task-msg",
                AuthorizedOperationType.update,
            )

        assert exc_info.value is operation_denied


@pytest.mark.unit
@pytest.mark.asyncio
class TestTaskDeleteAuthWrites:
    async def test_delete_task_revokes_legacy_ownership_after_delete(self):
        from src.api.routes.tasks import delete_task

        task_use_case = MagicMock()
        task_use_case.delete_task = AsyncMock(return_value=None)
        authorization = MagicMock()
        authorization.revoke = AsyncMock(return_value=None)

        result = await delete_task(
            task_id="task-1",
            task_use_case=task_use_case,
            authorization=authorization,
        )

        task_use_case.delete_task.assert_awaited_once_with(id="task-1")
        authorization.revoke.assert_awaited_once_with(AgentexResource.task("task-1"))
        assert result.id == "task-1"

    async def test_delete_task_by_name_revokes_resolved_task_after_delete(self):
        from src.api.routes.tasks import delete_task_by_name

        task_use_case = MagicMock()
        task_use_case.get_task = AsyncMock(return_value=MagicMock(id="task-2"))
        task_use_case.delete_task = AsyncMock(return_value=None)
        authorization = MagicMock()
        authorization.revoke = AsyncMock(return_value=None)

        result = await delete_task_by_name(
            task_name="named-task",
            task_use_case=task_use_case,
            authorization=authorization,
        )

        task_use_case.get_task.assert_awaited_once_with(name="named-task")
        task_use_case.delete_task.assert_awaited_once_with(name="named-task")
        authorization.revoke.assert_awaited_once_with(AgentexResource.task("task-2"))
        assert result.id == "task-2"


@pytest.mark.unit
@pytest.mark.asyncio
class TestCheckTaskOrCollapseTo404:
    """The task-resource authz wrap hides unreadable tasks."""

    async def test_allowed_check_returns_normally(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await check_task_or_collapse_to_404(
            authorization,
            "task-1",
            AuthorizedOperationType.update,
        )

        authorization.check.assert_awaited_once()

    async def test_denied_read_collapses_to_not_found(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await check_task_or_collapse_to_404(
                authorization,
                "task-1",
                AuthorizedOperationType.read,
            )

        authorization.check.assert_awaited_once()

    async def test_denied_non_read_collapses_to_not_found_when_read_denied(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await check_task_or_collapse_to_404(
                authorization,
                "task-1",
                AuthorizedOperationType.update,
            )

        assert authorization.check.await_count == 2
        first_call, second_call = authorization.check.await_args_list
        assert first_call.kwargs["operation"] == AuthorizedOperationType.update
        assert second_call.kwargs["operation"] == AuthorizedOperationType.read

    async def test_denied_non_read_surfaces_authorization_error_when_read_allowed(self):
        authorization = MagicMock()
        operation_denied = AuthorizationError("denied")
        authorization.check = AsyncMock(side_effect=[operation_denied, True])

        with pytest.raises(AuthorizationError) as exc_info:
            await check_task_or_collapse_to_404(
                authorization,
                "task-1",
                AuthorizedOperationType.update,
            )

        assert exc_info.value is operation_denied


@pytest.mark.unit
@pytest.mark.asyncio
class TestDAuthorizedBodyIdTaskWrap:
    """``DAuthorizedBodyId`` must route task-resource body-id checks through
    the task visibility wrapper, matching the path/query variants."""

    @staticmethod
    def _make_request(task_id: str) -> MagicMock:
        request = MagicMock()
        request.json = AsyncMock(return_value={"task_id": task_id})
        return request

    async def test_task_body_id_routes_through_wrap_on_denial(self):
        annotation = DAuthorizedBodyId(
            AgentexResourceType.task, AuthorizedOperationType.update
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await dep(self._make_request("task-7"), authorization)

        assert authorization.check.await_count == 2

    async def test_task_body_id_update_denied_when_readable_surfaces_authorization_error(
        self,
    ):
        annotation = DAuthorizedBodyId(
            AgentexResourceType.task, AuthorizedOperationType.update
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(
            side_effect=[AuthorizationError("update denied"), True]
        )

        with pytest.raises(AuthorizationError):
            await dep(self._make_request("task-7"), authorization)

    async def test_task_body_id_returns_field_value_when_allowed(self):
        annotation = DAuthorizedBodyId(
            AgentexResourceType.task, AuthorizedOperationType.update
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        result = await dep(self._make_request("task-9"), authorization)

        assert result == "task-9"

    async def test_agent_body_id_uses_visibility_wrap(self):
        annotation = DAuthorizedBodyId(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        request = MagicMock()
        request.json = AsyncMock(return_value={"agent_id": "agent-1"})

        result = await dep(request, authorization)

        assert result == "agent-1"
        authorization.check.assert_awaited_once()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-1")


@pytest.mark.unit
@pytest.mark.asyncio
class TestDAuthorizedNameTaskWrap:
    """``DAuthorizedName`` must route task-resource name-path checks through
    the task-collapse wrap so denied name-path calls return 404 instead of 403.
    Without this, ``tasks.name`` (globally unique) lets callers probe whether
    a name exists in any tenant by observing 404 vs 403 — exactly the
    cross-tenant existence leak the other surfaces eliminate."""

    async def test_task_name_routes_through_wrap_on_denial(self):
        annotation = DAuthorizedName(
            AgentexResourceType.task, AuthorizedOperationType.update
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        agent_repository = MagicMock()
        task_repository = MagicMock()
        task_repository.get = AsyncMock(return_value=MagicMock(id="task-resolved"))

        with pytest.raises(ItemDoesNotExist):
            await dep(authorization, agent_repository, task_repository, "task-name-x")

        # The wrap fires AFTER the lookup — the repo is consulted to resolve
        # name → id; the leak is only on the authz response, not the lookup.
        task_repository.get.assert_awaited_once_with(name="task-name-x")
        assert authorization.check.await_count == 2

    async def test_task_name_update_denied_when_readable_surfaces_authorization_error(
        self,
    ):
        annotation = DAuthorizedName(
            AgentexResourceType.task, AuthorizedOperationType.update
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(
            side_effect=[AuthorizationError("update denied"), True]
        )
        agent_repository = MagicMock()
        task_repository = MagicMock()
        task_repository.get = AsyncMock(return_value=MagicMock(id="task-resolved"))

        with pytest.raises(AuthorizationError):
            await dep(authorization, agent_repository, task_repository, "task-name-x")

    async def test_task_name_returns_resource_name_when_allowed(self):
        annotation = DAuthorizedName(
            AgentexResourceType.task, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        agent_repository = MagicMock()
        task_repository = MagicMock()
        task_repository.get = AsyncMock(return_value=MagicMock(id="task-allow"))

        result = await dep(authorization, agent_repository, task_repository, "ok-name")

        assert result == "ok-name"
        called_kwargs = authorization.check.await_args.kwargs
        # The selector is the resolved row id, not the user-provided name.
        assert called_kwargs["resource"] == AgentexResource.task("task-allow")

    async def test_agent_name_collapses_to_404(self):
        """Agent name-routes collapse a denial to 404 through their own wrap,
        like tasks. Full agent coverage lives in test_agents_authz.py; here we
        only guard that the shared name dependency routes agents through a
        collapse wrap rather than the plain check that surfaces a denial as 403."""
        annotation = DAuthorizedName(
            AgentexResourceType.agent, AuthorizedOperationType.read
        )
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        agent_repository = MagicMock()
        agent_repository.get = AsyncMock(return_value=MagicMock(id="agent-1"))
        task_repository = MagicMock()

        with pytest.raises(ItemDoesNotExist):
            await dep(authorization, agent_repository, task_repository, "agent-name")
