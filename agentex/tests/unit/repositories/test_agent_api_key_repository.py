import asyncio
import os

# Import the repository and entities we need to test
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from adapters.orm import BaseORM
from domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from domain.entities.agents import ACPType, AgentEntity, AgentStatus
from domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from domain.repositories.agent_repository import AgentRepository
from utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_api_key_repository_crud_operations(
    postgres_url, isolated_test_schema
):
    """Test comprehensive CRUD operations for AgentAPIKeyRepository"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness
    for attempt in range(10):
        try:
            engine = create_async_engine(
                sqlalchemy_asyncpg_url,
                echo=True,
                connect_args={
                    "server_settings": {
                        "search_path": isolated_test_schema["schema_name"]
                    }
                },
            )
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(BaseORM.metadata.create_all)
                # Test connectivity
                await conn.execute(text("SELECT 1"))
            break
        except Exception as e:
            if attempt < 9:
                print(
                    f"Database not ready (attempt {attempt + 1}), retrying... Error: {e}"
                )
                await asyncio.sleep(2)
                continue
            raise

    # Create async session maker
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # Create repositories
    agent_api_key_repo = AgentAPIKeyRepository(async_session_maker)
    agent_repo = AgentRepository(async_session_maker)

    # First, create an agent (required for api key creation)
    agent_id = orm_id()
    agent = AgentEntity(
        id=agent_id,
        name="test-agent-for-api-keys",
        description="Test agent for api key repository testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.AGENTIC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for task testing: {created_agent.id}")

    # Create a test api_key
    agent_api_key_id = orm_id()
    agent_api_key = AgentAPIKeyEntity(
        id=agent_api_key_id,
        name="test-api-key",
        agent_id=agent_id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="test-api-key",
    )

    # Test CREATE operation
    created_api_key = await agent_api_key_repo.create(agent_api_key)
    assert created_api_key.id == agent_api_key_id
    assert created_api_key.name == "test-api-key"
    assert created_api_key.agent_id == agent_id
    assert created_api_key.api_key_type == AgentAPIKeyType.EXTERNAL
    assert created_api_key.api_key == "test-api-key"
    assert created_api_key.created_at is not None
    print("✅ CREATE operation successful")

    # Test LIST operation
    all_api_keys = await agent_api_key_repo.list()
    assert len(all_api_keys) >= 1
    assert any(s.id == agent_api_key_id for s in all_api_keys)
    print("✅ LIST operation successful")

    # Create a second api_key to test multiple items
    agent_api_key_id_2 = orm_id()
    agent_api_key_2 = AgentAPIKeyEntity(
        id=agent_api_key_id_2,
        name="test-api-key-2",
        agent_id=agent_id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="test-api-key-2",
    )

    created_api_key_2 = await agent_api_key_repo.create(agent_api_key_2)
    assert created_api_key_2.id == agent_api_key_id_2

    # Test LIST with multiple api_keys
    all_api_keys_multi = await agent_api_key_repo.list()
    assert len(all_api_keys_multi) >= 2
    api_key_ids = [s.id for s in all_api_keys_multi]
    assert agent_api_key_id in api_key_ids
    assert agent_api_key_id_2 in api_key_ids
    print("✅ LIST multiple api_keys successful")

    # Test GET by name
    first_api_key = await agent_api_key_repo.get_by_agent_id_and_name(
        agent_id=agent_id, name="test-api-key", api_key_type=AgentAPIKeyType.EXTERNAL
    )
    assert first_api_key is not None
    assert first_api_key.id == agent_api_key_id
    assert first_api_key.name == "test-api-key"
    print("✅ GET by name operation successful")

    # Test GET by hash
    first_api_key_by = await agent_api_key_repo.get_external_by_agent_id_and_key(
        agent_id=agent_id, api_key="test-api-key"
    )
    assert first_api_key_by is not None
    assert first_api_key_by.id == agent_api_key_id
    assert first_api_key_by.api_key == "test-api-key"
    print("✅ GET by hash operation successful")

    # Test DELETE by name
    await agent_api_key_repo.delete_by_agent_id_and_key_name(
        agent_id=agent_id,
        key_name="test-api-key",
        api_key_type=AgentAPIKeyType.EXTERNAL,
    )
    deleted_api_key = await agent_api_key_repo.get_by_agent_id_and_name(
        agent_id=agent_id, name="test-api-key", api_key_type=AgentAPIKeyType.EXTERNAL
    )
    # Should return None since it was deleted
    assert deleted_api_key is None
    print("✅ DELETE by name operation successful")

    print("🎉 ALL AGENT API KEY REPOSITORY TESTS PASSED!")
