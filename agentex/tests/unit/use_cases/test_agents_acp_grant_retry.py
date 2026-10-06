from unittest.mock import AsyncMock, MagicMock

import pytest
from src.adapters.authentication.exceptions import (
    AuthenticationServiceUnavailableError,
)
from src.domain.use_cases import agents_acp_use_case
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase

pytestmark = pytest.mark.unit


def make_use_case(grant_error):
    task_service = MagicMock()
    task_service.fail_task = AsyncMock()
    authorization_service = MagicMock()
    authorization_service.grant = AsyncMock(side_effect=grant_error)
    use_case = AgentsACPUseCase(
        agent_repository=MagicMock(),
        deployment_repository=MagicMock(),
        acp_client=MagicMock(),
        task_service=task_service,
        task_message_service=MagicMock(),
        authorization_service=authorization_service,
    )
    return use_case, task_service, authorization_service


@pytest.mark.asyncio
async def test_persistent_auth_service_failure_fails_task(monkeypatch):
    monkeypatch.setattr(agents_acp_use_case.asyncio, "sleep", AsyncMock())
    error = AuthenticationServiceUnavailableError(
        message="Auth provider rejected this service's identity (forbidden)"
    )
    use_case, task_service, authorization_service = make_use_case(error)
    task = MagicMock(id="task-id")

    with pytest.raises(AuthenticationServiceUnavailableError):
        await use_case.grant_with_retry(task)

    assert authorization_service.grant.await_count == 4
    task_service.fail_task.assert_awaited_once_with(task, str(error))


@pytest.mark.asyncio
async def test_transient_auth_service_failure_does_not_fail_task(monkeypatch):
    monkeypatch.setattr(agents_acp_use_case.asyncio, "sleep", AsyncMock())
    use_case, task_service, authorization_service = make_use_case(
        [AuthenticationServiceUnavailableError(message="Auth provider error"), None]
    )

    await use_case.grant_with_retry(MagicMock(id="task-id"))

    assert authorization_service.grant.await_count == 2
    task_service.fail_task.assert_not_awaited()
