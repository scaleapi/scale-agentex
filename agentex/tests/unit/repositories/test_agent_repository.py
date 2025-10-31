import asyncio
import os

# Import the repository and entities we need to test
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from adapters.orm import BaseORM
from domain.entities.agents import ACPType, AgentEntity, AgentStatus
from domain.repositories.agent_repository import AgentRepository


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_repository_crud_operations(postgres_url, isolated_test_schema):
    """Test comprehensive CRUD operations for AgentRepository"""

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
                await conn.execute(text("SELECT 1"))
            break
        except Exception:
            if attempt == 9:
                raise
            await asyncio.sleep(0.2)

    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(BaseORM.metadata.create_all)

        # Test in a transaction that will rollback
        async with engine.begin() as conn:
            # Bind session to this connection for transactional isolation
            scoped_session_maker = async_sessionmaker(bind=conn)
            test_repository = AgentRepository(scoped_session_maker)

            # Test 1: Create an agent
            agent_data = AgentEntity(
                id=str(uuid4()),
                name="test-agent",
                description="A test agent for unit testing",
                docker_image="test/agent:latest",
                status=AgentStatus.READY,
                acp_type=ACPType.ASYNC,
                acp_url="http://localhost:8000/acp",
            )

            created_agent = await test_repository.create(agent_data)
            assert created_agent.id == agent_data.id
            assert created_agent.name == "test-agent"
            assert created_agent.status == AgentStatus.READY
            print("✅ CREATE operation successful")

            # Test 2: Get the agent by ID
            retrieved_agent = await test_repository.get(id=created_agent.id)
            assert retrieved_agent.id == created_agent.id
            assert retrieved_agent.name == "test-agent"
            assert retrieved_agent.description == "A test agent for unit testing"
            print("✅ GET by ID operation successful")

            # Test 3: Get the agent by name
            retrieved_by_name = await test_repository.get(name="test-agent")
            assert retrieved_by_name.id == created_agent.id
            assert retrieved_by_name.name == "test-agent"
            print("✅ GET by name operation successful")

            # Test 4: Update the agent
            updated_data = retrieved_agent.model_copy()
            updated_data.description = "Updated test agent description"
            updated_data.status = AgentStatus.FAILED

            updated_agent = await test_repository.update(updated_data)
            assert updated_agent.description == "Updated test agent description"
            assert updated_agent.status == AgentStatus.FAILED
            print("✅ UPDATE operation successful")

            # Test 5: List agents
            agent_list = await test_repository.list()
            assert len(agent_list) == 1
            assert agent_list[0].id == created_agent.id
            print("✅ LIST operation successful")

            # Test 6: Create another agent for batch operations
            agent_data_2 = AgentEntity(
                id=str(uuid4()),
                name="test-agent-2",
                description="Second test agent",
                status=AgentStatus.READY,
                acp_type=ACPType.SYNC,
            )

            created_agent_2 = await test_repository.create(agent_data_2)

            # Test 7: List multiple agents
            agent_list = await test_repository.list()
            assert len(agent_list) == 2
            agent_names = [agent.name for agent in agent_list]
            assert "test-agent" in agent_names
            assert "test-agent-2" in agent_names
            print("✅ LIST multiple agents successful")

            # Test 8: List multiple agents with pagination
            page_number = 1
            paged_agents = []
            while True:
                agent_list_with_page = await test_repository.list(
                    limit=1, page_number=page_number
                )
                paged_agents.extend(agent_list_with_page)
                if len(agent_list_with_page) < 1:
                    break
                assert len(agent_list_with_page) == 1
                page_number += 1
            assert len(paged_agents) == 2
            assert paged_agents[0].id == created_agent.id
            assert paged_agents[1].id == created_agent_2.id
            print("✅ LIST multiple agents with pagination successful")

            # Test 9: Delete an agent
            await test_repository.delete(id=created_agent_2.id)

            # Verify deletion
            agent_list_after_delete = await test_repository.list()
            assert len(agent_list_after_delete) == 1
            assert agent_list_after_delete[0].id == created_agent.id
            print("✅ DELETE operation successful")

            # Force rollback by raising exception
            raise Exception("Force transaction rollback for test isolation")

    except Exception as e:
        if "Force transaction rollback" not in str(e):
            raise
        print("✅ Transaction rollback forced for test isolation")

    finally:
        await engine.dispose()

    # Test 9: Verify rollback worked - create new engine and check
    engine2 = create_async_engine(
        sqlalchemy_asyncpg_url,
        echo=False,
        connect_args={
            "server_settings": {"search_path": isolated_test_schema["schema_name"]}
        },
    )
    try:
        session_maker2 = async_sessionmaker(engine2)
        repository2 = AgentRepository(session_maker2)

        # Should be empty after rollback
        agent_list = await repository2.list()
        assert (
            len(agent_list) == 0
        ), f"Expected 0 agents after rollback, got {len(agent_list)}"
        print("✅ TRANSACTION ROLLBACK verification successful")

    finally:
        await engine2.dispose()

    print("🎉 ALL AGENT REPOSITORY TESTS PASSED!")
