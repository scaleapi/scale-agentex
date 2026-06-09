"""Integration tests for ScheduleService authorization writes.

Schedules have no Postgres row: Temporal is the store and the auth selector is
``{agent_id}--{schedule_name}``. The authorization-write sequencing therefore
lives in ``ScheduleService`` next to the Temporal write:

- Create registers the schedule in the authorization graph under parent=agent,
  before the Temporal create.
- Registration failure prevents the Temporal create.
- A Temporal create failure after a successful registration triggers a
  best-effort compensating deregister and re-raises the original Temporal error.
- A post-create read-back failure does not deregister, because the schedule was
  actually created.
- Delete removes the Temporal schedule first, then deregisters best-effort.
- No creator identity means the registration is skipped and the schedule still
  lands in Temporal.

The tests mock the Temporal adapter and authorization service and stub the
post-create read-back; the behavior under test is the call sequencing inside
``ScheduleService``, not Temporal or the authorization service itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from src.api.schemas.authorization_types import AgentexResource, AgentexResourceType
from src.api.schemas.schedules import CreateScheduleRequest, ScheduleResponse
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.services.schedule_service import ScheduleService, build_schedule_id
from src.utils.ids import orm_id


def _principal(
    user_id: str | None = None, service_account_id: str | None = None
) -> SimpleNamespace:
    """Minimal stand-in for the auth principal context."""
    return SimpleNamespace(
        user_id=user_id, service_account_id=service_account_id, account_id="acct-1"
    )


def _agent() -> AgentEntity:
    agent_id = orm_id()
    return AgentEntity(
        id=agent_id,
        name=f"agent-{agent_id[:8]}",
        description="authorization-write test agent",
        status=AgentStatus.READY,
        acp_type=ACPType.SYNC,
        acp_url="http://test-acp",
    )


def _request(name: str = "nightly") -> CreateScheduleRequest:
    return CreateScheduleRequest(
        name=name,
        workflow_name="test-workflow",
        task_queue="test-queue",
        cron_expression="0 0 * * *",
    )


def _build_service(
    *,
    principal: SimpleNamespace | None,
    register_resource: AsyncMock | None = None,
    deregister_resource: AsyncMock | None = None,
    create_raises: Exception | None = None,
    delete_raises: Exception | None = None,
    get_schedule_raises: Exception | None = None,
) -> tuple[ScheduleService, Mock, Mock]:
    temporal_adapter = Mock()
    temporal_adapter.create_schedule = AsyncMock(
        side_effect=create_raises, return_value=None
    )
    temporal_adapter.delete_schedule = AsyncMock(
        side_effect=delete_raises, return_value=None
    )

    authorization_service = Mock()
    authorization_service.principal_context = principal
    authorization_service.register_resource = register_resource or AsyncMock(
        return_value=None
    )
    authorization_service.deregister_resource = deregister_resource or AsyncMock(
        return_value=None
    )

    service = ScheduleService(
        temporal_adapter=temporal_adapter,
        authorization_service=authorization_service,
    )
    # Stub the post-create read-back so create_schedule doesn't hit
    # describe_schedule; tests covering a read-back failure pass get_schedule_raises.
    if get_schedule_raises is not None:
        service.get_schedule = AsyncMock(side_effect=get_schedule_raises)
    else:
        service.get_schedule = AsyncMock(return_value=Mock(spec=ScheduleResponse))

    return service, temporal_adapter, authorization_service


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_calls_register_resource_with_parent() -> None:
    agent = _agent()
    request = _request("nightly")
    service, temporal_adapter, authorization_service = _build_service(
        principal=_principal(user_id="user-A"),
    )

    await service.create_schedule(agent, request)

    authorization_service.register_resource.assert_awaited_once()
    registered_resource: AgentexResource = (
        authorization_service.register_resource.await_args.kwargs["resource"]
    )
    assert registered_resource.type == AgentexResourceType.schedule
    assert registered_resource.selector == build_schedule_id(agent.id, request.name)
    registered_parent: AgentexResource = (
        authorization_service.register_resource.await_args.kwargs["parent"]
    )
    # parent_agent is load-bearing: without it the authorization cascade from
    # the owning agent fails closed for readers.
    assert registered_parent is not None
    assert registered_parent.type == AgentexResourceType.agent
    assert registered_parent.selector == agent.id
    temporal_adapter.create_schedule.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_schedule_calls_deregister_resource() -> None:
    agent = _agent()
    service, temporal_adapter, authorization_service = _build_service(
        principal=_principal(user_id="user-A"),
    )

    await service.delete_schedule(agent.id, "nightly")

    schedule_id = build_schedule_id(agent.id, "nightly")
    temporal_adapter.delete_schedule.assert_awaited_once_with(schedule_id)
    authorization_service.deregister_resource.assert_awaited_once()
    deregistered_resource: AgentexResource = (
        authorization_service.deregister_resource.await_args.kwargs["resource"]
    )
    assert deregistered_resource.type == AgentexResourceType.schedule
    assert deregistered_resource.selector == schedule_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_register_failure_prevents_temporal_create() -> None:
    register = AsyncMock(side_effect=RuntimeError("authz unavailable"))
    agent = _agent()
    service, temporal_adapter, authorization_service = _build_service(
        principal=_principal(user_id="user-A"),
        register_resource=register,
    )

    with pytest.raises(RuntimeError, match="authz unavailable"):
        await service.create_schedule(agent, _request())

    temporal_adapter.create_schedule.assert_not_awaited()
    authorization_service.deregister_resource.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_temporal_failure_triggers_compensating_deregister() -> (
    None
):
    agent = _agent()
    request = _request("nightly")
    service, _, authorization_service = _build_service(
        principal=_principal(user_id="user-A"),
        create_raises=RuntimeError("temporal down"),
    )

    with pytest.raises(RuntimeError, match="temporal down"):
        await service.create_schedule(agent, request)

    authorization_service.register_resource.assert_awaited_once()
    # The schedule never landed in Temporal, so the auth entry is cleaned up.
    authorization_service.deregister_resource.assert_awaited_once()
    compensated: AgentexResource = (
        authorization_service.deregister_resource.await_args.kwargs["resource"]
    )
    assert compensated.type == AgentexResourceType.schedule
    assert compensated.selector == build_schedule_id(agent.id, request.name)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_readback_failure_does_not_compensate() -> None:
    # The Temporal create succeeded but the post-create describe failed. The
    # schedule genuinely exists, so the auth entry must survive the read-back
    # error.
    agent = _agent()
    service, temporal_adapter, authorization_service = _build_service(
        principal=_principal(user_id="user-A"),
        get_schedule_raises=RuntimeError("describe transient error"),
    )

    with pytest.raises(RuntimeError, match="describe transient error"):
        await service.create_schedule(agent, _request())

    temporal_adapter.create_schedule.assert_awaited_once()
    authorization_service.register_resource.assert_awaited_once()
    authorization_service.deregister_resource.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_schedule_deregister_failure_does_not_block_delete() -> None:
    deregister = AsyncMock(side_effect=RuntimeError("authz unavailable"))
    agent = _agent()
    service, temporal_adapter, authorization_service = _build_service(
        principal=_principal(user_id="user-A"),
        deregister_resource=deregister,
    )

    # Best-effort cleanup: a deregister failure is swallowed after Temporal
    # delete succeeds.
    await service.delete_schedule(agent.id, "nightly")

    temporal_adapter.delete_schedule.assert_awaited_once_with(
        build_schedule_id(agent.id, "nightly")
    )
    authorization_service.deregister_resource.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_no_creator_skips_auth_writes() -> None:
    agent = _agent()
    request = _request("nightly")
    # Neither user_id nor service_account_id: internal paths still create the
    # schedule, but there is no creator identity to register as owner.
    service, temporal_adapter, authorization_service = _build_service(
        principal=_principal(user_id=None, service_account_id=None),
    )

    await service.create_schedule(agent, request)

    authorization_service.register_resource.assert_not_awaited()
    authorization_service.deregister_resource.assert_not_awaited()
    temporal_adapter.create_schedule.assert_awaited_once()
