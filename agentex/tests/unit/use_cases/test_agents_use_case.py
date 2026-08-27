from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.config.environment_variables import EnvironmentVariables
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.deployment_history_repository import (
    DeploymentHistoryRepository,
)
from src.domain.repositories.deployment_repository import DeploymentRepository
from src.domain.use_cases.agents_use_case import AgentsUseCase
from tests.fixtures.services import make_noop_authorization_service


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
def enable_health_check_workflow(monkeypatch):
    monkeypatch.setenv("ENABLE_HEALTH_CHECK_WORKFLOW", "true")
    monkeypatch.setenv("AGENTEX_SERVER_TASK_QUEUE", "agentex-server")
    EnvironmentVariables.clear_cache()
    yield
    EnvironmentVariables.clear_cache()


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
        authorization_service=make_noop_authorization_service(),
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


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize("register_by_id", [False, True])
async def test_deployment_aware_register_uses_deployment_acp_url_for_healthcheck(
    agents_use_case,
    agent_repository,
    deployment_repository,
    temporal_adapter,
    enable_health_check_workflow,
    register_by_id,
):
    name = f"build-only-deployment-aware-{uuid4().hex[:8]}"
    deployment_id = str(uuid4())
    deployment_acp_url = "http://deployment.example.com"
    build_only_agent = await agents_use_case.register_build(
        name=name,
        description="build-only agent",
    )
    temporal_adapter.start_workflow.reset_mock()

    await agents_use_case.register_agent(
        name=name,
        description="build-only agent",
        acp_url=deployment_acp_url,
        agent_id=build_only_agent.id if register_by_id else None,
        acp_type=ACPType.ASYNC,
        registration_metadata={
            "deployment_id": deployment_id,
            "docker_image": "example:preview",
        },
    )

    refreshed_agent = await agent_repository.get(id=build_only_agent.id)
    deployment = await deployment_repository.get(id=deployment_id)

    assert refreshed_agent.acp_url is None
    assert deployment.acp_url == deployment_acp_url
    temporal_adapter.start_workflow.assert_awaited_once()
    assert temporal_adapter.start_workflow.await_args.kwargs["args"] == [
        {"agent_id": build_only_agent.id, "acp_url": deployment_acp_url}
    ]


async def _seed_agent_with_card_metadata(
    agent_repository: AgentRepository,
    name: str,
    card_metadata: dict | None,
) -> AgentEntity:
    registration_metadata: dict = {}
    if card_metadata is not None:
        registration_metadata["agent_card"] = {"metadata": card_metadata}
    return await agent_repository.create(
        AgentEntity(
            id=str(uuid4()),
            name=name,
            description="seed",
            status=AgentStatus.READY,
            acp_type=ACPType.ASYNC,
            acp_url="http://seed.example.com",
            registration_metadata=registration_metadata or None,
        )
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_filters_by_agent_card_metadata_exact_containment(
    agents_use_case, agent_repository
):
    """Filter matches only agents whose card metadata contains every requested pair.

    Uses a per-test-unique tag so assertions are robust to data seeded by other
    tests sharing the same session-scoped Postgres container.
    """
    suffix = uuid4().hex[:6]
    tag = f"test-{suffix}"
    permits = await _seed_agent_with_card_metadata(
        agent_repository,
        f"card-metadata-permits-{suffix}",
        {"permits_capable": True, "region": "us", "test_tag": tag},
    )
    other = await _seed_agent_with_card_metadata(
        agent_repository,
        f"card-metadata-other-{suffix}",
        {"other_feature": True, "test_tag": tag},
    )
    plain = await _seed_agent_with_card_metadata(
        agent_repository,
        f"card-metadata-none-{suffix}",
        None,
    )
    scoped_ids = {permits.id, other.id, plain.id}

    # Single-key exact filter, scoped to this test's tag → only permits agent.
    matches = await agents_use_case.list(
        limit=50,
        page_number=1,
        agent_card_metadata={"permits_capable": True, "test_tag": tag},
    )
    assert {a.id for a in matches if a.id in scoped_ids} == {permits.id}

    # Non-matching value under our tag returns no agents seeded by this test.
    no_matches = await agents_use_case.list(
        limit=50,
        page_number=1,
        agent_card_metadata={"permits_capable": False, "test_tag": tag},
    )
    assert {a.id for a in no_matches if a.id in scoped_ids} == set()

    # Multi-key containment requires every key/value to be present.
    multi = await agents_use_case.list(
        limit=50,
        page_number=1,
        agent_card_metadata={
            "permits_capable": True,
            "region": "us",
            "test_tag": tag,
        },
    )
    assert {a.id for a in multi if a.id in scoped_ids} == {permits.id}
    missing_key = await agents_use_case.list(
        limit=50,
        page_number=1,
        agent_card_metadata={
            "permits_capable": True,
            "region": "eu",
            "test_tag": tag,
        },
    )
    assert {a.id for a in missing_key if a.id in scoped_ids} == set()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_without_agent_card_metadata_returns_all_non_deleted(
    agents_use_case, agent_repository
):
    """Omitting the filter preserves existing behavior (agents without card metadata still listed)."""
    suffix = uuid4().hex[:6]
    with_card = await _seed_agent_with_card_metadata(
        agent_repository,
        f"card-metadata-with-{suffix}",
        {"permits_capable": True},
    )
    without_card = await _seed_agent_with_card_metadata(
        agent_repository,
        f"card-metadata-without-{suffix}",
        None,
    )

    all_agents = await agents_use_case.list(limit=50, page_number=1)
    all_ids = {a.id for a in all_agents}
    assert {with_card.id, without_card.id} <= all_ids
