"""Tests for the agent_schedule route migration to fine-grained authorization.

Mirrors the structure of the agent_api_key and task route-authorization tests.
Covers:

  1. The ``_check_schedule_or_collapse_to_404`` helper (allow + denied-collapse).
  2. ``DAuthorizedScheduleId`` builds the composite ``{agent_id}--{schedule_name}``
     selector, returns the schedule name when allowed, and collapses denials to
     404 (the no-existence-leak path).
  3. ``create_schedule`` enforces parent ``agent.update`` (the only route where
     no schedule resource exists yet, so the authorization service can't
     transitively gate it).
  4. ``ScheduleService.list_schedules`` filters to the authorized id set, with
     ``None`` (bypass) returning everything and ``[]`` returning nothing.

Cross-tenant and transitive-expansion checks belong in an end-to-end suite
gated on a live authorization-service cluster (the ``agent_schedule.update``
permission transitively requires ``parent_agent->update`` in the authorization
policy, which this repo does not own). Here we only assert that the route layer
issues the correct ``check`` call with the correct operation and surfaces
denials as 404.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.domain.services.schedule_service import ScheduleService, build_schedule_id
from src.utils.schedule_authorization import _check_schedule_or_collapse_to_404


def _dep_callable(annotation):
    """Pull the inner FastAPI dependency function out of an ``Annotated[str, Depends(...)]``."""
    return annotation.__metadata__[0].dependency


@pytest.mark.unit
@pytest.mark.asyncio
class TestCheckScheduleOrCollapseTo404:
    """The schedule-resource authz wrap collapses every denial to 404 so callers
    can't distinguish "present in another tenant" from "absent"."""

    async def test_allowed_check_returns_normally(self):
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_schedule_or_collapse_to_404(
            authorization,
            "agent-1--nightly",
            AuthorizedOperationType.read,
        )

        authorization.check.assert_awaited_once()
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.schedule("agent-1--nightly")
        assert called_kwargs["operation"] == AuthorizedOperationType.read

    async def test_denied_collapses_to_not_found_regardless_of_existence(self):
        """Both "denied + schedule exists" and "denied + schedule missing"
        surface as ``ItemDoesNotExist`` (→ 404). The wrap doesn't consult
        Temporal — collapsing avoids the cross-tenant existence leak."""
        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        with pytest.raises(ItemDoesNotExist):
            await _check_schedule_or_collapse_to_404(
                authorization,
                "agent-1--nightly",
                AuthorizedOperationType.delete,
            )

    async def test_forwards_operation_verbatim(self):
        """The transitive expansion for ``update``/``delete`` in the
        authorization policy is what bundles in the ``parent_agent->update``
        factor — the helper just needs to forward the operation."""
        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        await _check_schedule_or_collapse_to_404(
            authorization,
            "agent-1--nightly",
            AuthorizedOperationType.update,
        )

        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["operation"] == AuthorizedOperationType.update


@pytest.mark.unit
@pytest.mark.asyncio
class TestSingleResourceRouteAuthz:
    """The single-resource routes (get/pause/unpause/trigger/delete) check the
    schedule resource on the composite ``{agent_id}--{schedule_name}`` selector
    inline, collapsing denials to 404 — mirroring the agent_api_key name routes.
    Verifies per-route operation routing and that a denial skips the use case."""

    async def test_get_authorized_checks_read_and_calls_use_case(self):
        from src.api.routes.schedules import get_schedule

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        use_case = MagicMock()
        use_case.get_schedule = AsyncMock(return_value=MagicMock())

        await get_schedule(
            agent_id="agent-1",
            schedule_name="nightly",
            schedules_use_case=use_case,
            authorization=authorization,
        )

        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule(
            build_schedule_id("agent-1", "nightly")
        )
        assert called["operation"] == AuthorizedOperationType.read
        use_case.get_schedule.assert_awaited_once_with("agent-1", "nightly")

    async def test_get_denied_collapses_to_404_and_skips_use_case(self):
        from src.api.routes.schedules import get_schedule

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        use_case = MagicMock()
        use_case.get_schedule = AsyncMock()

        with pytest.raises(ItemDoesNotExist):
            await get_schedule(
                agent_id="agent-1",
                schedule_name="nightly",
                schedules_use_case=use_case,
                authorization=authorization,
            )
        # The check runs before the Temporal lookup, so a denial never reaches it.
        use_case.get_schedule.assert_not_called()

    async def test_pause_uses_update_op(self):
        from src.api.routes.schedules import pause_schedule

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)
        use_case = MagicMock()
        use_case.pause_schedule = AsyncMock(return_value=MagicMock())

        await pause_schedule(
            agent_id="agent-1",
            schedule_name="nightly",
            schedules_use_case=use_case,
            authorization=authorization,
            request=None,
        )

        called = authorization.check.await_args.kwargs
        assert called["resource"] == AgentexResource.schedule("agent-1--nightly")
        assert called["operation"] == AuthorizedOperationType.update

    async def test_delete_uses_delete_op_and_denied_skips_delete(self):
        from src.api.routes.schedules import delete_schedule

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))
        use_case = MagicMock()
        use_case.delete_schedule = AsyncMock()

        with pytest.raises(ItemDoesNotExist):
            await delete_schedule(
                agent_id="agent-1",
                schedule_name="nightly",
                schedules_use_case=use_case,
                authorization=authorization,
            )
        use_case.delete_schedule.assert_not_called()
        assert (
            authorization.check.await_args.kwargs["operation"]
            == AuthorizedOperationType.delete
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateParentAgentCheck:
    """``create_schedule`` is the only route where no schedule resource exists
    yet, so the authorization service cannot transitively gate on it. The
    route's ``agent_id`` guard MUST check ``agent.update`` on the parent, and a
    denial collapses to 404 — like every other agent check — so the schedules
    endpoint can't be used to probe cross-tenant agent existence."""

    @staticmethod
    def _agent_id_dep():
        from src.api.routes.schedules import create_schedule

        return _dep_callable(create_schedule.__annotations__["agent_id"])

    async def test_create_checks_parent_agent_update(self):
        dep = self._agent_id_dep()

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        # Repos are unused on the agent path; bind resource_id by keyword so an
        # added repo dep fails loudly instead of silently mis-binding the id.
        result = await dep(
            authorization, MagicMock(), MagicMock(), MagicMock(), resource_id="agent-1"
        )

        assert result == "agent-1"
        called_kwargs = authorization.check.await_args.kwargs
        assert called_kwargs["resource"] == AgentexResource.agent("agent-1")
        assert called_kwargs["operation"] == AuthorizedOperationType.update

    async def test_create_denied_collapses_to_404(self):
        dep = self._agent_id_dep()

        authorization = MagicMock()
        authorization.check = AsyncMock(side_effect=AuthorizationError("denied"))

        # Parent-agent denial collapses to 404 so creating a schedule under an
        # agent in another tenant can't reveal that the agent exists.
        with pytest.raises(ItemDoesNotExist):
            await dep(
                authorization,
                MagicMock(),
                MagicMock(),
                MagicMock(),
                resource_id="agent-1",
            )


def _fake_schedule(schedule_id: str, *, paused: bool = False):
    """Minimal stand-in for a Temporal schedule list entry.

    ``list_schedules`` reads ``.id`` and ``.info.{action,next_action_times,
    paused}``; a non-``ScheduleActionStartWorkflow`` action yields
    ``workflow_name=None`` and an empty ``next_action_times`` yields
    ``next_action_time=None``, both valid for ``ScheduleListItem``.
    """
    info = SimpleNamespace(action=None, next_action_times=[], paused=paused)
    return SimpleNamespace(id=schedule_id, info=info)


@pytest.mark.unit
@pytest.mark.asyncio
class TestListOwnershipFiltering:
    """``ScheduleService.list_schedules`` filters the Temporal page to the
    authorized id set. ``None`` (authz bypass) returns everything; ``[]`` (caller
    owns nothing) returns nothing — gating on ``is not None``, not truthiness."""

    @staticmethod
    def _service():
        temporal_adapter = MagicMock()
        temporal_adapter.list_schedules = AsyncMock(
            return_value=[
                _fake_schedule("agent-1--alpha"),
                _fake_schedule("agent-1--beta"),
                _fake_schedule("agent-2--gamma"),
            ]
        )
        return ScheduleService(
            temporal_adapter=temporal_adapter,
            authorization_service=MagicMock(),
        )

    async def test_none_returns_all_for_agent(self):
        service = self._service()

        response = await service.list_schedules(
            agent_id="agent-1", authorized_schedule_ids=None
        )

        ids = {item.schedule_id for item in response.schedules}
        assert ids == {"agent-1--alpha", "agent-1--beta"}

    async def test_empty_list_returns_nothing(self):
        service = self._service()

        response = await service.list_schedules(
            agent_id="agent-1", authorized_schedule_ids=[]
        )

        assert response.schedules == []
        assert response.total == 0

    async def test_subset_filters_to_authorized_ids(self):
        service = self._service()

        response = await service.list_schedules(
            agent_id="agent-1", authorized_schedule_ids=["agent-1--alpha"]
        )

        ids = {item.schedule_id for item in response.schedules}
        assert ids == {"agent-1--alpha"}

    async def test_authorized_id_under_other_agent_is_excluded(self):
        """The agent_id scope is applied first, so an authorized id belonging to
        a different agent never leaks into this agent's listing."""
        service = self._service()

        response = await service.list_schedules(
            agent_id="agent-1", authorized_schedule_ids=["agent-2--gamma"]
        )

        assert response.schedules == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestUseCaseForwardsAuthorizedIds:
    """The use case is a thin pass-through; it must forward the ownership filter
    to the service unchanged."""

    async def test_list_forwards_authorized_schedule_ids(self):
        from src.domain.use_cases.schedules_use_case import SchedulesUseCase

        schedule_service = MagicMock()
        schedule_service.list_schedules = AsyncMock(return_value=MagicMock())
        use_case = SchedulesUseCase(schedule_service=schedule_service)

        await use_case.list_schedules(
            "agent-1", page_size=50, authorized_schedule_ids=["agent-1--alpha"]
        )

        schedule_service.list_schedules.assert_awaited_once_with(
            agent_id="agent-1",
            page_size=50,
            authorized_schedule_ids=["agent-1--alpha"],
        )
