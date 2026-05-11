from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.deployment_history_repository import (
    DeploymentHistoryRepository,
)
from src.domain.repositories.deployment_repository import DeploymentRepository
from src.domain.use_cases.agents_use_case import AgentsUseCase


@pytest.fixture
def agent_repository(postgres_session_maker):
    return AgentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def deployment_repository(postgres_session_maker):
    return DeploymentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def deployment_history_repository(postgres_session_maker):
    return DeploymentHistoryRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def temporal_adapter():
    return AsyncMock(spec=TemporalAdapter)


@pytest.fixture
def agents_use_case(
    agent_repository,
    deployment_history_repository,
    deployment_repository,
    temporal_adapter,
):
    return AgentsUseCase(
        agent_repository=agent_repository,
        deployment_history_repository=deployment_history_repository,
        deployment_repository=deployment_repository,
        temporal_adapter=temporal_adapter,
    )


async def _seed_agent_with_production_deployment(
    agent_repository: AgentRepository,
    deployment_repository: DeploymentRepository,
    name: str,
) -> tuple[AgentEntity, DeploymentEntity]:
    agent_id = str(uuid4())
    deployment_id = str(uuid4())

    agent = await agent_repository.create(
        AgentEntity(
            id=agent_id,
            name=name,
            description="seed agent",
            status=AgentStatus.READY,
            acp_type=ACPType.ASYNC,
            acp_url="http://prod-deployment.example.com",
        )
    )
    deployment = await deployment_repository.create(
        DeploymentEntity(
            id=deployment_id,
            agent_id=agent.id,
            docker_image="example:prod",
            status=DeploymentStatus.READY,
            acp_url="http://prod-deployment.example.com",
            is_production=True,
        )
    )
    agent.production_deployment_id = deployment.id
    agent = await agent_repository.update(agent)
    return agent, deployment


@pytest.mark.asyncio
@pytest.mark.unit
async def test_legacy_register_with_agent_id_clears_production_state(
    agents_use_case, agent_repository, deployment_repository
):
    name = f"legacy-agent-id-{uuid4().hex[:8]}"
    agent, deployment = await _seed_agent_with_production_deployment(
        agent_repository, deployment_repository, name
    )

    await agents_use_case.register_agent(
        name=name,
        description="updated description",
        acp_url="http://legacy.example.com",
        agent_id=agent.id,
        acp_type=ACPType.ASYNC,
        registration_metadata=None,
    )

    refreshed_agent = await agent_repository.get(id=agent.id)
    refreshed_deployment = await deployment_repository.get(id=deployment.id)

    assert refreshed_agent.production_deployment_id is None
    assert refreshed_agent.acp_url == "http://legacy.example.com"
    assert refreshed_deployment.is_production is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_legacy_register_by_name_clears_production_state(
    agents_use_case, agent_repository, deployment_repository
):
    name = f"legacy-by-name-{uuid4().hex[:8]}"
    agent, deployment = await _seed_agent_with_production_deployment(
        agent_repository, deployment_repository, name
    )

    await agents_use_case.register_agent(
        name=name,
        description="updated description",
        acp_url="http://legacy.example.com",
        acp_type=ACPType.ASYNC,
        registration_metadata=None,
    )

    refreshed_agent = await agent_repository.get(id=agent.id)
    refreshed_deployment = await deployment_repository.get(id=deployment.id)

    assert refreshed_agent.production_deployment_id is None
    assert refreshed_agent.acp_url == "http://legacy.example.com"
    assert refreshed_deployment.is_production is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deployment_aware_register_on_virgin_agent_does_not_auto_promote(
    agents_use_case, agent_repository, deployment_repository
):
    name = f"virgin-deployment-aware-{uuid4().hex[:8]}"
    deployment_id = str(uuid4())

    agent = await agents_use_case.register_agent(
        name=name,
        description="new agent",
        acp_url="http://deployment.example.com",
        acp_type=ACPType.ASYNC,
        registration_metadata={
            "deployment_id": deployment_id,
            "docker_image": "example:preview",
        },
    )

    refreshed_agent = await agent_repository.get(id=agent.id)
    deployment = await deployment_repository.get(id=deployment_id)

    assert refreshed_agent.production_deployment_id is None
    assert deployment.is_production is False
    assert deployment.acp_url == "http://deployment.example.com"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deployment_aware_register_on_legacy_agent_does_not_auto_promote(
    agents_use_case, agent_repository, deployment_repository
):
    name = f"legacy-then-deployment-{uuid4().hex[:8]}"
    legacy_agent = await agents_use_case.register_agent(
        name=name,
        description="legacy agent",
        acp_url="http://legacy.example.com",
        acp_type=ACPType.ASYNC,
        registration_metadata=None,
    )

    deployment_id = str(uuid4())
    await agents_use_case.register_agent(
        name=name,
        description="legacy agent",
        acp_url="http://preview.example.com",
        acp_type=ACPType.ASYNC,
        registration_metadata={
            "deployment_id": deployment_id,
            "docker_image": "example:preview",
        },
    )

    refreshed_agent = await agent_repository.get(id=legacy_agent.id)
    deployment = await deployment_repository.get(id=deployment_id)

    assert refreshed_agent.production_deployment_id is None
    assert refreshed_agent.acp_url == "http://legacy.example.com"
    assert deployment.is_production is False
    assert deployment.acp_url == "http://preview.example.com"
