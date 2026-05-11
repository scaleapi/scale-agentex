from uuid import uuid4

import pytest
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.deployment_repository import DeploymentRepository


@pytest.fixture
def agent_repository(postgres_session_maker):
    return AgentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def deployment_repository(postgres_session_maker):
    return DeploymentRepository(postgres_session_maker, postgres_session_maker)


async def _create_agent_with_production_deployment(
    agent_repository: AgentRepository,
    deployment_repository: DeploymentRepository,
) -> tuple[AgentEntity, DeploymentEntity]:
    agent_id = str(uuid4())
    deployment_id = str(uuid4())

    agent = await agent_repository.create(
        AgentEntity(
            id=agent_id,
            name=f"agent-{agent_id[:8]}",
            description="test agent",
            status=AgentStatus.READY,
            acp_type=ACPType.ASYNC,
            acp_url="http://legacy.example.com",
        )
    )

    deployment = await deployment_repository.create(
        DeploymentEntity(
            id=deployment_id,
            agent_id=agent.id,
            docker_image="example:latest",
            status=DeploymentStatus.READY,
            acp_url="http://deployment.example.com",
            is_production=True,
        )
    )

    agent.production_deployment_id = deployment.id
    agent = await agent_repository.update(agent)
    return agent, deployment


@pytest.mark.asyncio
@pytest.mark.unit
async def test_clear_production_nulls_agent_pointer_and_demotes_deployment(
    agent_repository, deployment_repository
):
    agent, deployment = await _create_agent_with_production_deployment(
        agent_repository, deployment_repository
    )

    await deployment_repository.clear_production(agent_id=agent.id)

    refreshed_agent = await agent_repository.get(id=agent.id)
    refreshed_deployment = await deployment_repository.get(id=deployment.id)

    assert refreshed_agent.production_deployment_id is None
    assert refreshed_deployment.is_production is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_clear_production_is_noop_when_no_production_deployment(
    agent_repository, deployment_repository
):
    agent_id = str(uuid4())
    agent = await agent_repository.create(
        AgentEntity(
            id=agent_id,
            name=f"agent-{agent_id[:8]}",
            description="test agent",
            status=AgentStatus.READY,
            acp_type=ACPType.ASYNC,
            acp_url="http://legacy.example.com",
        )
    )

    await deployment_repository.clear_production(agent_id=agent.id)

    refreshed_agent = await agent_repository.get(id=agent.id)
    assert refreshed_agent.production_deployment_id is None
