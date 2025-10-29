from datetime import UTC, datetime
from uuid import uuid4

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.deployment_history_repository import (
    DeploymentHistoryRepository,
)
from src.domain.use_cases.deployment_history_use_case import DeploymentHistoryUseCase


@pytest.fixture
def agent_repository(postgres_session_maker):
    """Real AgentRepository using test PostgreSQL database"""
    return AgentRepository(postgres_session_maker)


@pytest.fixture
def deployment_history_repository(postgres_session_maker):
    """Real DeploymentHistoryRepository using test PostgreSQL database"""
    return DeploymentHistoryRepository(postgres_session_maker)


@pytest.fixture
def deployment_history_use_case(deployment_history_repository):
    """Real DeploymentHistoryUseCase instance with real repository"""
    return DeploymentHistoryUseCase(
        deployment_history_repository=deployment_history_repository
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for deployment history testing",
        acp_type=ACPType.ASYNC,
        status=AgentStatus.READY,
        acp_url="http://test-acp.example.com",
    )


async def create_or_get_agent(agent_repository, agent):
    """Helper to create agent or get existing one"""
    try:
        return await agent_repository.create(agent)
    except Exception:
        # Agent might already exist, sync the ID
        try:
            existing = await agent_repository.get(name=agent.name)
            agent.id = existing.id
            return existing
        except ItemDoesNotExist:
            raise


@pytest.mark.asyncio
@pytest.mark.unit
class TestDeploymentHistoryUseCase:
    """Test suite for DeploymentHistoryUseCase"""

    async def test_create_and_retrieve_deployment(
        self, deployment_history_use_case, agent_repository, sample_agent
    ):
        """Test creating and retrieving a deployment record"""
        # Given - An agent exists
        await create_or_get_agent(agent_repository, sample_agent)

        # When - Create a deployment record
        result = await deployment_history_use_case.create_deployment(
            agent_id=sample_agent.id,
            author_name="John Doe",
            author_email="john.doe@example.com",
            branch_name="test-branch",
            build_timestamp=datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC),
            deployment_timestamp=datetime(2025, 10, 1, 12, 5, 0, tzinfo=UTC),
            commit_hash="abc123def456",
        )

        # Then - Deployment should be created successfully
        assert result.agent_id == sample_agent.id
        assert result.author_name == "John Doe"
        assert result.author_email == "john.doe@example.com"
        assert result.branch_name == "test-branch"
        assert result.commit_hash == "abc123def456"
        assert result.id is not None

        # And - Should be retrievable by ID
        retrieved = await deployment_history_use_case.get_deployment(result.id)
        assert retrieved.id == result.id
        assert retrieved.agent_id == sample_agent.id
        assert retrieved.branch_name == "test-branch"
        assert retrieved.commit_hash == "abc123def456"

    async def test_list_deployments_with_filters(
        self, deployment_history_use_case, agent_repository, sample_agent
    ):
        """Test listing deployments with various filters"""
        # Given - An agent exists
        await create_or_get_agent(agent_repository, sample_agent)

        # And - Multiple deployment records exist
        deployment1 = await deployment_history_use_case.create_deployment(
            agent_id=sample_agent.id,
            author_name="John Doe",
            author_email="john.doe@example.com",
            branch_name="test-branch",
            build_timestamp=datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC),
            deployment_timestamp=datetime(2025, 10, 1, 12, 5, 0, tzinfo=UTC),
            commit_hash="commit1",
        )

        deployment2 = await deployment_history_use_case.create_deployment(
            agent_id=sample_agent.id,
            author_name="Jane Smith",
            author_email="jane.smith@example.com",
            branch_name="test-branch",
            build_timestamp=datetime(2025, 10, 2, 12, 0, 0, tzinfo=UTC),
            deployment_timestamp=datetime(2025, 10, 2, 12, 5, 0, tzinfo=UTC),
            commit_hash="commit2",
        )

        # When - List all deployments
        all_deployments = await deployment_history_use_case.list_deployments(
            limit=100, page_number=1
        )

        # Then - Should return both deployments
        assert len(all_deployments) >= 2
        deployment_ids = [d.id for d in all_deployments]
        assert deployment1.id in deployment_ids
        assert deployment2.id in deployment_ids

        # When - Filter by agent ID
        agent_deployments = await deployment_history_use_case.list_deployments(
            agent_id=sample_agent.id, limit=100, page_number=1
        )

        # Then - Should return deployments for that agent
        assert len(agent_deployments) >= 2
        for deployment in agent_deployments:
            assert deployment.agent_id == sample_agent.id

        # When - Filter by commit hash
        commit_deployments = await deployment_history_use_case.list_deployments(
            commit_hash="commit1", limit=100, page_number=1
        )

        # Then - Should return the matching deployment
        assert len(commit_deployments) == 1
        assert commit_deployments[0].commit_hash == "commit1"

        # When - Filter by author email
        jane_deployments = await deployment_history_use_case.list_deployments(
            author_email="jane.smith@example.com", limit=100, page_number=1
        )

        # Then - Should find Jane's deployment
        assert len(jane_deployments) == 1
        assert jane_deployments[0].author_email == "jane.smith@example.com"

    async def test_get_recent_deployments_for_agent(
        self, deployment_history_use_case, agent_repository, sample_agent
    ):
        """Test getting recent deployments for a specific agent"""
        # Given - An agent exists
        await create_or_get_agent(agent_repository, sample_agent)

        # And - Multiple deployment records exist for the agent
        deployments = []
        for i in range(5):
            deployment = await deployment_history_use_case.create_deployment(
                agent_id=sample_agent.id,
                author_name=f"Author {i}",
                author_email=f"author{i}@example.com",
                branch_name="test-branch",
                build_timestamp=datetime(2025, 11, 1, 12, i, 0, tzinfo=UTC),
                deployment_timestamp=datetime(2025, 11, 1, 12, i + 1, 0, tzinfo=UTC),
                commit_hash=f"commit{i}",
            )
            deployments.append(deployment)

        # When - Get recent deployments with default limit
        last_deployment = (
            await deployment_history_use_case.get_last_deployment_for_agent(
                agent_id=sample_agent.id
            )
        )

        # Then - Should return deployments for the agent
        assert last_deployment is not None
        assert last_deployment.agent_id == sample_agent.id
        assert last_deployment.id == deployments[-1].id

    async def test_deployment_not_found(self, deployment_history_use_case):
        """Test handling of non-existent deployment"""
        # Given - A non-existent deployment ID
        non_existent_id = str(uuid4())

        # When - Try to get the deployment
        # Then - Should raise ItemDoesNotExist
        with pytest.raises(ItemDoesNotExist):
            await deployment_history_use_case.get_deployment(non_existent_id)

    async def test_multiple_agents_same_commit(
        self, deployment_history_use_case, agent_repository
    ):
        """Test that multiple agents can have deployments with the same commit hash"""
        # Given - Two different agents exist
        agent1 = AgentEntity(
            id=str(uuid4()),
            name="test-agent-1",
            description="First test agent",
            acp_type=ACPType.ASYNC,
            status=AgentStatus.READY,
            acp_url="http://test-acp1.example.com",
        )
        agent2 = AgentEntity(
            id=str(uuid4()),
            name="test-agent-2",
            description="Second test agent",
            acp_type=ACPType.ASYNC,
            status=AgentStatus.READY,
            acp_url="http://test-acp2.example.com",
        )

        await create_or_get_agent(agent_repository, agent1)
        await create_or_get_agent(agent_repository, agent2)

        # When - Create deployments with same commit hash for different agents
        same_commit_hash = "shared-commit-123"

        deployment1 = await deployment_history_use_case.create_deployment(
            agent_id=agent1.id,
            author_name="John Doe",
            author_email="john.doe@example.com",
            branch_name="test-branch",
            build_timestamp=datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC),
            deployment_timestamp=datetime(2025, 10, 1, 12, 5, 0, tzinfo=UTC),
            commit_hash=same_commit_hash,
        )

        deployment2 = await deployment_history_use_case.create_deployment(
            agent_id=agent2.id,
            author_name="John Doe",
            author_email="john.doe@example.com",
            branch_name="test-branch",
            build_timestamp=datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC),
            deployment_timestamp=datetime(2025, 10, 1, 12, 10, 0, tzinfo=UTC),
            commit_hash=same_commit_hash,
        )

        # Then - Both deployments should be created successfully
        assert deployment1.id != deployment2.id
        assert deployment1.agent_id != deployment2.agent_id
        assert deployment1.commit_hash == deployment2.commit_hash == same_commit_hash

        # And - Should be able to retrieve deployments by commit hash
        # Note: get_by_commit_hash might return any one of them since commit hash is not unique
        commit_deployments = await deployment_history_use_case.list_deployments(
            commit_hash="shared-commit-123", limit=100, page_number=1
        )
        assert len(commit_deployments) == 2

        # And - Should be able to filter by agent to get specific deployments
        agent1_deployments = await deployment_history_use_case.list_deployments(
            agent_id=agent1.id, limit=100, page_number=1
        )
        agent1_with_commit = [
            d for d in agent1_deployments if d.commit_hash == same_commit_hash
        ]
        assert len(agent1_with_commit) == 1
        assert agent1_with_commit[0].id == deployment1.id

        agent2_deployments = await deployment_history_use_case.list_deployments(
            agent_id=agent2.id, limit=100, page_number=1
        )
        agent2_with_commit = [
            d for d in agent2_deployments if d.commit_hash == same_commit_hash
        ]
        assert len(agent2_with_commit) == 1
        assert agent2_with_commit[0].id == deployment2.id
