from unittest.mock import AsyncMock

import pytest
from src.domain.entities.agents import AgentEntity, AgentStatus
from src.domain.use_cases.agents_use_case import AgentsUseCase


def _use_case():
    agent = AgentEntity(
        id="agent-1",
        name="agent",
        description="test agent",
        status=AgentStatus.READY,
        acp_url="http://agent",
    )
    agent_repo = AsyncMock()
    agent_repo.get.return_value = agent
    agent_repo.update.return_value = agent
    temporal_adapter = AsyncMock()
    authorization_service = AsyncMock()
    use_case = AgentsUseCase(
        agent_repository=agent_repo,
        deployment_history_repository=AsyncMock(),
        deployment_repository=AsyncMock(),
        temporal_adapter=temporal_adapter,
        authorization_service=authorization_service,
    )
    return use_case, agent, agent_repo, temporal_adapter


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_terminates_healthcheck_workflow():
    use_case, agent, _, temporal_adapter = _use_case()

    deleted = await use_case.delete(id=agent.id)

    assert deleted.status == AgentStatus.DELETED
    temporal_adapter.terminate_workflow.assert_awaited_once_with(
        workflow_id="healthcheck_workflow_agent-1",
        reason="Agent deleted",
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_survives_healthcheck_termination_failure():
    use_case, agent, agent_repo, temporal_adapter = _use_case()
    temporal_adapter.terminate_workflow.side_effect = RuntimeError("Temporal down")

    deleted = await use_case.delete(id=agent.id)

    assert deleted.status == AgentStatus.DELETED
    agent_repo.update.assert_awaited_once_with(agent)
