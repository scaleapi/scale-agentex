"""Integration tests for task dual-write to the authorization service.

Covers register-before-persist ordering, compensating deregister on persist
failure, deregister-after-delete, and no-op when the task name doesn't resolve.

- ``create_task`` registers the task (with the agent as ``parent``) *before*
  persisting the Postgres row.
- If the persist fails after a successful register, ``create_task`` issues a
  compensating ``deregister_resource`` and re-raises.
- ``delete_task`` deregisters *after* the Postgres delete, best-effort: a
  deregister failure is swallowed (Postgres is the source of truth for
  existence) so a delete that already succeeded does not surface an error.

The register-before-persist and delete paths run as integration tests because
they touch the real task repository through ``isolated_repositories``; the
compensation test uses a mock repository so the persist can be forced to fail.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import AgentexResource, AgentexResourceType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.services.task_service import AgentTaskService


def _build_service(*, task_repository) -> tuple[AgentTaskService, Mock]:
    authorization_service = Mock()
    authorization_service.principal_context = None
    authorization_service.grant = AsyncMock(return_value={})
    authorization_service.revoke = AsyncMock(return_value=None)
    authorization_service.register_resource = AsyncMock(return_value=None)
    authorization_service.deregister_resource = AsyncMock(return_value=None)

    service = AgentTaskService(
        acp_client=Mock(),
        task_state_repository=Mock(),
        task_repository=task_repository,
        event_repository=Mock(),
        stream_repository=Mock(),
        authorization_service=authorization_service,
    )
    return service, authorization_service


def _agent_entity() -> AgentEntity:
    return AgentEntity(
        id=str(uuid4()),
        name=f"dual-write-agent-{uuid4().hex[:8]}",
        description="dual-write test agent",
        status=AgentStatus.READY,
        acp_type=ACPType.SYNC,
        acp_url="http://test-acp",
    )


async def _persist_agent(agent_repository) -> AgentEntity:
    return await agent_repository.create(_agent_entity())


async def _task_exists(task_repository, task_id: str) -> bool:
    try:
        await task_repository.get(id=task_id)
        return True
    except ItemDoesNotExist:
        return False


async def _clear_task_agent_links(task_repository, task_id: str) -> None:
    """Delete the task_agents / agent_task_tracker join rows for a task.

    ``create_task`` writes both join rows, and ``task_repository.delete``
    issues a raw ``DELETE FROM tasks`` that the ``task_agents_task_id_fkey``
    FK rejects while those rows exist — this is the established, intentional
    contract (see ``test_task_repository.test_delete_task`` and
    ``test_task_service.test_delete_task_with_cleanup``). Tests that exercise
    the hard-delete deregister path must clear the join rows first, exactly as
    a real cascading delete would, otherwise the delete FK-fails before the
    deregister dual-write is ever reached.
    """
    from sqlalchemy import delete as sql_delete
    from src.adapters.orm import AgentTaskTrackerORM, TaskAgentORM

    async with task_repository.start_async_db_session(True) as session:
        await session.execute(
            sql_delete(AgentTaskTrackerORM).where(
                AgentTaskTrackerORM.task_id == task_id
            )
        )
        await session.execute(
            sql_delete(TaskAgentORM).where(TaskAgentORM.task_id == task_id)
        )
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskDualWrite:
    async def test_create_task_registers_before_persist_with_agent_as_parent(
        self, isolated_repositories
    ):
        task_repo = isolated_repositories["task_repository"]
        agent_repo = isolated_repositories["agent_repository"]
        agent = await _persist_agent(agent_repo)
        service, authorization_service = _build_service(task_repository=task_repo)

        # When register fires, the Postgres row must not exist yet — this is
        # what makes a registration failure abort the request cleanly.
        observed = {}

        async def _record_existence(resource, parent=None):
            observed["row_exists_at_register"] = await _task_exists(
                task_repo, resource.selector
            )

        authorization_service.register_resource.side_effect = _record_existence

        task = await service.create_task(
            agent=agent, task_name=f"dw-create-{uuid4().hex[:8]}"
        )

        assert observed["row_exists_at_register"] is False
        assert await _task_exists(task_repo, task.id) is True

        authorization_service.register_resource.assert_awaited_once()
        call = authorization_service.register_resource.call_args
        registered_resource: AgentexResource = call.args[0]
        assert registered_resource.type == AgentexResourceType.task
        assert registered_resource.selector == task.id

        parent: AgentexResource | None = call.kwargs.get("parent")
        assert parent is not None
        assert parent.type == AgentexResourceType.agent
        assert parent.selector == agent.id

    async def test_create_compensates_with_deregister_when_persist_fails(self):
        # Register succeeds, then the Postgres persist blows up. create_task
        # must deregister the just-registered task (so no orphan authz tuple is
        # left for a task that never persisted) and re-raise.
        task_repo = Mock()
        task_repo.create = AsyncMock(side_effect=RuntimeError("db down"))
        service, authorization_service = _build_service(task_repository=task_repo)

        with pytest.raises(RuntimeError):
            await service.create_task(
                agent=_agent_entity(), task_name=f"dw-fail-{uuid4().hex[:8]}"
            )

        authorization_service.register_resource.assert_awaited_once()
        authorization_service.deregister_resource.assert_awaited_once()
        registered = authorization_service.register_resource.call_args.args[0]
        compensated = authorization_service.deregister_resource.call_args.args[0]
        assert compensated.type == AgentexResourceType.task
        assert compensated.selector == registered.selector

    async def test_delete_task_deregisters_after_delete(self, isolated_repositories):
        task_repo = isolated_repositories["task_repository"]
        agent_repo = isolated_repositories["agent_repository"]
        agent = await _persist_agent(agent_repo)
        service, authorization_service = _build_service(task_repository=task_repo)
        task = await service.create_task(
            agent=agent, task_name=f"dw-delete-{uuid4().hex[:8]}"
        )
        authorization_service.deregister_resource.reset_mock()
        await _clear_task_agent_links(task_repo, task.id)

        await service.delete_task(id=task.id)

        assert await _task_exists(task_repo, task.id) is False
        authorization_service.deregister_resource.assert_awaited_once()
        deregistered: AgentexResource = (
            authorization_service.deregister_resource.call_args.args[0]
        )
        assert deregistered.type == AgentexResourceType.task
        assert deregistered.selector == task.id

    async def test_delete_task_swallows_deregister_failure(self, isolated_repositories):
        # Postgres is the source of truth for existence: a deregister failure
        # after a successful delete leaves an orphan tuple (invisible to reads)
        # rather than failing a delete that already happened.
        task_repo = isolated_repositories["task_repository"]
        agent_repo = isolated_repositories["agent_repository"]
        agent = await _persist_agent(agent_repo)
        service, authorization_service = _build_service(task_repository=task_repo)
        task = await service.create_task(
            agent=agent, task_name=f"dw-dereg-fail-{uuid4().hex[:8]}"
        )
        await _clear_task_agent_links(task_repo, task.id)
        authorization_service.deregister_resource.reset_mock()
        authorization_service.deregister_resource.side_effect = RuntimeError(
            "authz down"
        )

        # Must not raise despite the deregister failure.
        await service.delete_task(id=task.id)

        assert await _task_exists(task_repo, task.id) is False
        authorization_service.deregister_resource.assert_awaited_once()

    async def test_delete_task_by_missing_name_does_not_deregister(
        self, isolated_repositories
    ):
        # The pre-delete id lookup catches ItemDoesNotExist, so a missing name
        # neither deregisters nor changes the underlying delete's error contract.
        task_repo = isolated_repositories["task_repository"]
        service, authorization_service = _build_service(task_repository=task_repo)

        await service.delete_task(name=f"missing-{uuid4().hex[:8]}")

        authorization_service.deregister_resource.assert_not_awaited()
