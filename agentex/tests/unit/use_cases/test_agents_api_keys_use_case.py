from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.use_cases.agent_api_keys_use_case import AgentAPIKeysUseCase


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for testing external API calls"""
    mock = AsyncMock()
    return mock


@pytest.fixture
def agent_repository(postgres_session_maker):
    """Real AgentRepository using test PostgreSQL database"""
    return AgentRepository(postgres_session_maker)


@pytest.fixture
def agent_api_key_repository(postgres_session_maker):
    """Real AgentAPIKeyRepository using test PostgreSQL database"""
    return AgentAPIKeyRepository(postgres_session_maker)


@pytest.fixture
def agent_api_keys_use_case(
    agent_api_key_repository, agent_repository, mock_http_client
):
    """Real AgentAPIKeysUseCase instance with real repositories"""
    return AgentAPIKeysUseCase(
        agent_api_key_repository=agent_api_key_repository,
        agent_repository=agent_repository,
        client=mock_http_client,
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for use case testing",
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
class TestAgentAPIKeysUseCase:
    """Test suite for AgentAPIKeysUseCase"""

    async def test_create_wrong_agent_id(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test creating a new API key with a wrong agent ID"""
        with pytest.raises(HTTPException):
            await agent_api_keys_use_case.create(
                name="test-api-key",
                agent_id="non-existent-id",
                api_key_type=AgentAPIKeyType.EXTERNAL,
                api_key="test-api-key-value",
            )

    async def test_delete_by_agent_name(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test deleting an API key with agent name"""
        await create_or_get_agent(agent_repository, sample_agent)
        result = await agent_api_keys_use_case.create(
            name="test-api-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        assert result is not None

        await agent_api_keys_use_case.delete_by_agent_name_and_key_name(
            agent_name=sample_agent.name,
            key_name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        find_by_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_name is None

        with pytest.raises(ItemDoesNotExist):
            await agent_api_keys_use_case.delete_by_agent_name_and_key_name(
                agent_name=sample_agent.name,
                key_name="test-api-key",
                api_key_type=AgentAPIKeyType.EXTERNAL,
            )

    async def test_delete_by_agent_id(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test deleting an API key with agent ID"""
        await create_or_get_agent(agent_repository, sample_agent)
        result = await agent_api_keys_use_case.create(
            name="test-api-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        assert result is not None

        await agent_api_keys_use_case.delete_by_agent_id_and_key_name(
            agent_id=sample_agent.id,
            key_name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        find_by_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_name is None

        with pytest.raises(ItemDoesNotExist):
            await agent_api_keys_use_case.delete_by_agent_id_and_key_name(
                agent_id=sample_agent.id,
                key_name="test-api-key",
                api_key_type=AgentAPIKeyType.EXTERNAL,
            )

    async def test_create_external_api_key(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test creating a new API key"""
        await create_or_get_agent(agent_repository, sample_agent)
        result = await agent_api_keys_use_case.create(
            name="test-api-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        assert result.name == "test-api-key"
        assert result.agent_id == sample_agent.id
        assert result.api_key_type == AgentAPIKeyType.EXTERNAL
        assert result.api_key is not None

        find_by_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_name is not None
        assert find_by_name.name == "test-api-key"

        find_by_wrong_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="non-existent-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_wrong_name is None

        find_by_wrong_id = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id="non-existent-id",
            name="non-existent-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_wrong_id is None

        find_by_key = await agent_api_keys_use_case.get_external_by_agent_id_and_key(
            agent_id=sample_agent.id, api_key=result.api_key
        )
        assert find_by_key is not None
        assert find_by_key.api_key == result.api_key
        assert find_by_key.name == "test-api-key"

        find_by_wrong_key = (
            await agent_api_keys_use_case.get_external_by_agent_id_and_key(
                agent_id=sample_agent.id, api_key="non-existent-key"
            )
        )
        assert find_by_wrong_key is None

        await agent_api_keys_use_case.delete_by_agent_id_and_key_name(
            agent_id=sample_agent.id,
            key_name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        find_after_delete = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_after_delete is None
