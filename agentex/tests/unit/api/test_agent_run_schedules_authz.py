"""Route-level authorization tests for agent run schedules.

The service tests cover schedule behavior; these tests keep the HTTP route
wiring honest: selector shape, operation choice, create's parent-agent gate, and
list's ownership-filter dependency.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.routes.agent_run_schedules import (
    create_run_schedule,
    delete_run_schedule,
    get_run_schedule,
    get_run_schedule_by_name,
    list_run_schedules,
    pause_run_schedule,
    resume_run_schedule,
    trigger_run_schedule,
    update_run_schedule,
)
from src.api.schemas.agent_run_schedules import (
    CreateAgentRunScheduleRequest,
    ScheduleInitialInput,
    UpdateAgentRunScheduleRequest,
)
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.services.agent_run_schedule_service import (
    build_run_schedule_authz_selector,
)
from src.utils.authorization_shortcuts import DAuthorizedResourceIds
from src.utils.schedule_authorization import _check_schedule_or_collapse_to_404


def _dep_callable(annotation):
    """Pull the inner FastAPI dependency out of an Annotated Depends."""
    return annotation.__metadata__[0].dependency


def _authz_selector(agent_id: str = "agent-1", schedule_id: str = "schedule-1") -> str:
    return build_run_schedule_authz_selector(agent_id, schedule_id)


@pytest.mark.unit
@pytest.mark.asyncio
class TestCheckScheduleOrCollapseTo404:
    async def test_allowed_check_returns_normally(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_schedule_or_collapse_to_404(
            authorization,
            _authz_selector(),
            AuthorizedOperationType.read,
        )

        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule(_authz_selector())
        assert called["operation"] == AuthorizedOperationType.read

    async def test_denied_read_collapses_to_not_found(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await _check_schedule_or_collapse_to_404(
                authorization,
                _authz_selector(),
                AuthorizedOperationType.read,
            )

        authorization.check.assert_awaited_once()

    async def test_denied_non_read_collapses_when_read_denied(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await _check_schedule_or_collapse_to_404(
                authorization,
                _authz_selector(),
                AuthorizedOperationType.delete,
            )

        assert authorization.check.await_count == 2
        first_call, second_call = authorization.check.await_args_list
        assert first_call.kwargs["operation"] == AuthorizedOperationType.delete
        assert second_call.kwargs["operation"] == AuthorizedOperationType.read

    async def test_denied_non_read_surfaces_when_read_allowed(self):
        authorization = MagicMock()
        operation_denied = AuthorizationError("denied")
        authorization.check = AsyncMock(side_effect=[operation_denied, True])

        with pytest.raises(AuthorizationError) as exc_info:
            await _check_schedule_or_collapse_to_404(
                authorization,
                _authz_selector(),
                AuthorizedOperationType.delete,
            )

        assert exc_info.value is operation_denied


@pytest.mark.unit
@pytest.mark.asyncio
class TestSingleResourceRouteAuthz:
    async def test_get_checks_read_and_calls_use_case(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        use_case = MagicMock()
        use_case.get_schedule = AsyncMock(return_value=MagicMock())

        await get_run_schedule(
            agent_id="agent-1",
            schedule_id="schedule-1",
            run_schedules_use_case=use_case,
            authorization=authorization,
        )

        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule(_authz_selector())
        assert called["operation"] == AuthorizedOperationType.read
        use_case.get_schedule.assert_awaited_once_with("agent-1", "schedule-1")

    async def test_get_by_name_resolves_id_then_checks_read(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        use_case = MagicMock()
        use_case.get_schedule_id_by_name = AsyncMock(return_value="schedule-1")
        use_case.get_schedule = AsyncMock(return_value=MagicMock())

        await get_run_schedule_by_name(
            agent_id="agent-1",
            name="nightly",
            run_schedules_use_case=use_case,
            authorization=authorization,
        )

        use_case.get_schedule_id_by_name.assert_awaited_once_with("agent-1", "nightly")
        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule(_authz_selector())
        assert called["operation"] == AuthorizedOperationType.read
        use_case.get_schedule.assert_awaited_once_with("agent-1", "schedule-1")

    async def test_get_denied_collapses_to_404_and_skips_use_case(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        use_case = MagicMock()
        use_case.get_schedule = AsyncMock()

        with pytest.raises(ItemDoesNotExist):
            await get_run_schedule(
                agent_id="agent-1",
                schedule_id="schedule-1",
                run_schedules_use_case=use_case,
                authorization=authorization,
            )

        use_case.get_schedule.assert_not_called()

    @pytest.mark.parametrize(
        ("route", "method_name"),
        [
            (pause_run_schedule, "pause_schedule"),
            (resume_run_schedule, "resume_schedule"),
            (trigger_run_schedule, "trigger_schedule"),
        ],
    )
    async def test_mutation_routes_use_update_op(self, route, method_name):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        use_case = MagicMock()
        setattr(use_case, method_name, AsyncMock(return_value=MagicMock()))

        await route(
            agent_id="agent-1",
            schedule_id="schedule-1",
            run_schedules_use_case=use_case,
            authorization=authorization,
        )

        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule(_authz_selector())
        assert called["operation"] == AuthorizedOperationType.update
        getattr(use_case, method_name).assert_awaited_once()

    async def test_update_route_uses_update_op(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        use_case = MagicMock()
        use_case.update_schedule = AsyncMock(return_value=MagicMock())
        request = UpdateAgentRunScheduleRequest(description="new")

        await update_run_schedule(
            agent_id="agent-1",
            schedule_id="schedule-1",
            request=request,
            run_schedules_use_case=use_case,
            authorization=authorization,
        )

        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule(_authz_selector())
        assert called["operation"] == AuthorizedOperationType.update
        use_case.update_schedule.assert_awaited_once_with(
            "agent-1", "schedule-1", request
        )

    async def test_delete_uses_delete_op_and_denial_skips_delete(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        use_case = MagicMock()
        use_case.delete_schedule = AsyncMock()

        with pytest.raises(ItemDoesNotExist):
            await delete_run_schedule(
                agent_id="agent-1",
                schedule_id="schedule-1",
                run_schedules_use_case=use_case,
                authorization=authorization,
            )

        use_case.delete_schedule.assert_not_called()
        first_call, second_call = authorization.check.await_args_list
        assert first_call.kwargs["operation"] == AuthorizedOperationType.delete
        assert second_call.kwargs["operation"] == AuthorizedOperationType.read


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateParentAgentCheck:
    @staticmethod
    def _agent_id_dep():
        return _dep_callable(create_run_schedule.__annotations__["agent_id"])

    async def test_create_checks_parent_agent_update(self):
        dep = self._agent_id_dep()
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        result = await dep(
            authorization,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            resource_id="agent-1",
        )

        assert result == "agent-1"
        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.agent("agent-1")
        assert called["operation"] == AuthorizedOperationType.update

    async def test_create_denied_collapses_to_404(self):
        dep = self._agent_id_dep()
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await dep(
                authorization,
                MagicMock(),
                MagicMock(),
                MagicMock(),
                resource_id="agent-1",
            )

    async def test_create_denied_when_parent_readable_surfaces_403(self):
        dep = self._agent_id_dep()
        authorization = MagicMock()
        authorization.check = AsyncMock(
            side_effect=[AuthorizationError("update denied"), True]
        )

        with pytest.raises(AuthorizationError):
            await dep(
                authorization,
                MagicMock(),
                MagicMock(),
                MagicMock(),
                resource_id="agent-1",
            )

    async def test_create_route_fetches_agent_and_captures_creator_principal(self):
        agents_use_case = MagicMock()
        agent = MagicMock(id="agent-1")
        agents_use_case.get = AsyncMock(return_value=agent)
        run_schedules_use_case = MagicMock()
        run_schedules_use_case.create_schedule = AsyncMock(return_value=MagicMock())
        request = CreateAgentRunScheduleRequest(
            name="nightly",
            interval_seconds=3600,
            initial_input=ScheduleInitialInput(content="hello"),
        )
        http_request = SimpleNamespace(
            state=SimpleNamespace(
                principal_context={
                    "principal_type": "user",
                    "user_id": "user-1",
                    "account_id": "account-1",
                    "authorization": "Bearer secret",
                }
            )
        )

        await create_run_schedule(
            agent_id="agent-1",
            request=request,
            http_request=http_request,
            agents_use_case=agents_use_case,
            run_schedules_use_case=run_schedules_use_case,
        )

        agents_use_case.get.assert_awaited_once_with(id="agent-1")
        run_schedules_use_case.create_schedule.assert_awaited_once_with(
            agent,
            request,
            {
                "principal_type": "user",
                "user_id": "user-1",
                "account_id": "account-1",
            },
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestListOwnershipFiltering:
    async def test_list_route_forwards_authorized_ids_and_limit(self):
        use_case = MagicMock()
        use_case.list_schedules = AsyncMock(return_value=MagicMock())

        await list_run_schedules(
            agent_id="agent-1",
            run_schedules_use_case=use_case,
            authorized_schedule_ids=[_authz_selector("agent-1", "schedule-1")],
            limit=5,
        )

        use_case.list_schedules.assert_awaited_once_with(
            "agent-1",
            authorized_schedule_ids=[_authz_selector("agent-1", "schedule-1")],
            limit=5,
        )

    async def test_authorized_resource_ids_dependency_lists_schedule_reads(self):
        dep = _dep_callable(
            DAuthorizedResourceIds(
                AgentexResourceType.schedule, AuthorizedOperationType.read
            )
        )
        authorization = MagicMock()
        authorization.list_resources = AsyncMock(return_value=[_authz_selector()])

        result = await dep(authorization)

        assert result == [_authz_selector()]
        authorization.list_resources.assert_awaited_once_with(
            filter_resource=AgentexResourceType.schedule,
            filter_operation=AuthorizedOperationType.read,
        )

    async def test_authorized_resource_ids_dependency_preserves_bypass_none(self):
        dep = _dep_callable(DAuthorizedResourceIds(AgentexResourceType.schedule))
        authorization = MagicMock()
        authorization.list_resources = AsyncMock(return_value=None)

        result = await dep(authorization)

        assert result is None
