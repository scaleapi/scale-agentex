"""Integration tests for ScheduleService dual-write to Spark AuthZ.

scale-agentex calls ``register_resource`` / ``deregister_resource``
unconditionally; per-account routing (Spark vs legacy SGP) is owned by
agentex-auth so scale-agentex does NOT couple to a feature-flag service.

Schedule-specific shape (vs the agent_api_key dual-write): schedules have no
Postgres row — Temporal is the store and the auth selector is the schedule id
``{agent_id}--{schedule_name}``. The dual-write is therefore Temporal + Spark,
so the dual-write lives in ``ScheduleService`` (where the Temporal write is)
rather than the use case, and the compensation boundary is scoped to the
Temporal create only:

- Create registers register_resource with parent=agent (the parent_agent edge
  is load-bearing for the SpiceDB cascade) BEFORE the Temporal create.
- Register failure prevents the Temporal create (fail-closed).
- A Temporal create failure after a successful register triggers a
  compensating deregister (best-effort), then the original error re-raises.
- A post-create read-back (describe) failure does NOT compensate — the
  schedule was actually created, so its tuple must survive.
- Delete calls deregister_resource after the Temporal delete; a deregister
  failure does not block the delete.
- No creator → no register: if neither user_id nor service_account_id is
  resolvable, the dual-write is a no-op (logged) and the schedule is still
  created.

The tests mock the Temporal adapter and authorization service and stub the
post-create read-back; the behaviour under test is the call sequencing inside
``ScheduleService`` — not Temporal or Spark itself.
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
        description="dual-write test agent",
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
) -> tuple[ScheduleService, Mock, AsyncMock, AsyncMock]:
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

    return (
        service,
        temporal_adapter,
        authorization_service.register_resource,
        authorization_service.deregister_resource,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_calls_register_resource_with_parent() -> None:
    agent = _agent()
    request = _request("nightly")
    service, temporal_adapter, register, _ = _build_service(
        principal=_principal(user_id="user-A"),
    )

    await service.create_schedule(agent, request)

    register.assert_awaited_once()
    registered_resource: AgentexResource = register.await_args.kwargs["resource"]
    assert registered_resource.type == AgentexResourceType.schedule
    assert registered_resource.selector == build_schedule_id(agent.id, request.name)
    # parent_agent edge is load-bearing — without it the SpiceDB cascade
    # `read = ... & parent_agent->read` fails closed for every reader.
    registered_parent: AgentexResource = register.await_args.kwargs["parent"]
    assert registered_parent is not None
    assert registered_parent.type == AgentexResourceType.agent
    assert registered_parent.selector == agent.id
    temporal_adapter.create_schedule.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_schedule_calls_deregister_resource() -> None:
    agent = _agent()
    service, temporal_adapter, _, deregister = _build_service(
        principal=_principal(user_id="user-A"),
    )

    await service.delete_schedule(agent.id, "nightly")

    schedule_id = build_schedule_id(agent.id, "nightly")
    temporal_adapter.delete_schedule.assert_awaited_once_with(schedule_id)
    deregister.assert_awaited_once()
    deregistered_resource: AgentexResource = deregister.await_args.kwargs["resource"]
    assert deregistered_resource.type == AgentexResourceType.schedule
    assert deregistered_resource.selector == schedule_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_register_failure_prevents_temporal_create() -> None:
    register = AsyncMock(side_effect=RuntimeError("spark unavailable"))
    agent = _agent()
    service, temporal_adapter, _, _ = _build_service(
        principal=_principal(user_id="user-A"),
        register_resource=register,
    )

    with pytest.raises(RuntimeError, match="spark unavailable"):
        await service.create_schedule(agent, _request())

    # Fail-closed: the Temporal create never runs when register fails.
    temporal_adapter.create_schedule.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_temporal_failure_triggers_compensating_deregister() -> (
    None
):
    agent = _agent()
    request = _request("nightly")
    service, _, register, deregister = _build_service(
        principal=_principal(user_id="user-A"),
        create_raises=RuntimeError("temporal down"),
    )

    with pytest.raises(RuntimeError, match="temporal down"):
        await service.create_schedule(agent, request)

    register.assert_awaited_once()
    # Orphan-tuple guard: the tuple was registered but the Temporal create
    # failed, so the tuple is compensated away.
    deregister.assert_awaited_once()
    compensated: AgentexResource = deregister.await_args.kwargs["resource"]
    assert compensated.type == AgentexResourceType.schedule
    assert compensated.selector == build_schedule_id(agent.id, request.name)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_readback_failure_does_not_compensate() -> None:
    # The Temporal create SUCCEEDS but the post-create describe read-back fails.
    # The schedule genuinely exists, so its tuple must NOT be compensated away —
    # deregistering here would fail-close the owner out of their own schedule.
    agent = _agent()
    service, temporal_adapter, register, deregister = _build_service(
        principal=_principal(user_id="user-A"),
        get_schedule_raises=RuntimeError("describe transient error"),
    )

    with pytest.raises(RuntimeError, match="describe transient error"):
        await service.create_schedule(agent, _request())

    temporal_adapter.create_schedule.assert_awaited_once()
    register.assert_awaited_once()
    deregister.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_schedule_deregister_failure_does_not_block_delete() -> None:
    deregister = AsyncMock(side_effect=RuntimeError("spark unavailable"))
    agent = _agent()
    service, temporal_adapter, _, _ = _build_service(
        principal=_principal(user_id="user-A"),
        deregister_resource=deregister,
    )

    # Best-effort: the deregister failure is swallowed, the delete completes.
    await service.delete_schedule(agent.id, "nightly")

    temporal_adapter.delete_schedule.assert_awaited_once_with(
        build_schedule_id(agent.id, "nightly")
    )
    deregister.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_schedule_no_creator_skips_register() -> None:
    agent = _agent()
    request = _request("nightly")
    # Neither user_id nor service_account_id — agent-bypass / internal path.
    service, temporal_adapter, register, deregister = _build_service(
        principal=_principal(user_id=None, service_account_id=None),
    )

    await service.create_schedule(agent, request)

    register.assert_not_awaited()
    deregister.assert_not_awaited()
    # The schedule is still created — the dual-write is a no-op, not a block.
    temporal_adapter.create_schedule.assert_awaited_once()
