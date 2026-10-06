from unittest.mock import AsyncMock, MagicMock

import pytest
from src.adapters.authentication.exceptions import (
    AuthenticationServiceUnavailableError,
)
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.services.task_service import AgentTaskService
from src.domain.use_cases import agents_acp_use_case
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(agents_acp_use_case.asyncio, "sleep", AsyncMock())


def make_use_case(grant_error):
    authorization_service = MagicMock()
    authorization_service.grant = AsyncMock(side_effect=grant_error)
    authorization_service.register_resource = AsyncMock()
    authorization_service.deregister_resource = AsyncMock()
    task_repository = MagicMock()
    task_repository.get = AsyncMock(side_effect=ItemDoesNotExist("not found"))
    task_repository.create = AsyncMock(side_effect=lambda agent_id, task: task)
    task_service = AgentTaskService(
        acp_client=MagicMock(),
        task_state_repository=MagicMock(),
        task_repository=task_repository,
        event_repository=MagicMock(),
        stream_repository=MagicMock(),
        authorization_service=authorization_service,
    )
    use_case = AgentsACPUseCase(
        agent_repository=MagicMock(),
        deployment_repository=MagicMock(),
        acp_client=MagicMock(),
        task_service=task_service,
        task_message_service=MagicMock(),
        authorization_service=authorization_service,
    )
    return use_case, task_repository, authorization_service


AGENT = AgentEntity(
    id="agent-id",
    name="agent",
    description="",
    status=AgentStatus.READY,
    acp_type=ACPType.ASYNC,
    acp_url="http://agent",
)


async def test_persistent_auth_service_failure_does_not_persist_task():
    error = AuthenticationServiceUnavailableError(
        message="Auth provider rejected this service's identity (forbidden)"
    )
    use_case, task_repository, authorization_service = make_use_case(error)

    with pytest.raises(AuthenticationServiceUnavailableError):
        await use_case._get_or_create_task(agent=AGENT, task_name="run:s:f")

    assert authorization_service.grant.await_count == 4
    task_repository.create.assert_not_awaited()
    authorization_service.deregister_resource.assert_awaited_once()


async def test_retry_after_persistent_failure_grants_new_task():
    unavailable = AuthenticationServiceUnavailableError(message="Auth provider error")
    use_case, task_repository, authorization_service = make_use_case(
        [unavailable] * 4 + [None]
    )

    with pytest.raises(AuthenticationServiceUnavailableError):
        await use_case._get_or_create_task(agent=AGENT, task_name="run:s:f")
    task = await use_case._get_or_create_task(agent=AGENT, task_name="run:s:f")

    assert authorization_service.grant.await_count == 5
    granted = authorization_service.grant.await_args.kwargs["resource"]
    assert granted.selector == task.id
    task_repository.create.assert_awaited_once()


async def test_deregister_failure_does_not_mask_grant_error():
    error = AuthenticationServiceUnavailableError(message="Auth provider error")
    use_case, task_repository, authorization_service = make_use_case(error)
    authorization_service.deregister_resource.side_effect = RuntimeError("down")

    with pytest.raises(AuthenticationServiceUnavailableError):
        await use_case._get_or_create_task(agent=AGENT, task_name="run:s:f")
    task_repository.create.assert_not_awaited()


async def test_transient_auth_service_failure_persists_task():
    use_case, task_repository, authorization_service = make_use_case(
        [AuthenticationServiceUnavailableError(message="Auth provider error"), None]
    )

    task = await use_case._get_or_create_task(agent=AGENT, task_name="run:s:f")

    assert authorization_service.grant.await_count == 2
    task_repository.create.assert_awaited_once()
    assert task.name == "run:s:f"
