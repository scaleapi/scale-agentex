import asyncio
import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from adapters.orm import BaseORM
from domain.entities.states import StateEntity
from domain.repositories.task_state_postgres_repository import (
    TaskStatePostgresRepository,
)
from utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_state_postgres_repository_crud_operations(postgres_url):
    """Test TaskStatePostgresRepository CRUD operations with JSONB state fields."""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
            async with engine.begin() as conn:
                await conn.run_sync(BaseORM.metadata.create_all)
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

    # Create async session maker and repository
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    state_repo = TaskStatePostgresRepository(async_session_maker, async_session_maker)

    # Test CREATE operation with complex state data
    task_id = orm_id()
    agent_id = orm_id()
    state_id = orm_id()

    state_data = {
        "current_step": "processing",
        "context": {
            "user_input": "Hello world",
            "variables": {"name": "test", "count": 42},
        },
        "history": [
            {"step": "init", "timestamp": "2024-01-01T00:00:00Z"},
            {"step": "validate", "timestamp": "2024-01-01T00:01:00Z"},
        ],
        "metadata": {
            "version": "1.0",
            "environment": "test",
            "flags": ["debug", "verbose"],
        },
    }

    state = StateEntity(
        id=state_id,
        task_id=task_id,
        agent_id=agent_id,
        state=state_data,
    )

    created_state = await state_repo.create(state)
    assert created_state.id == state_id
    assert created_state.task_id == task_id
    assert created_state.agent_id == agent_id
    assert created_state.state["current_step"] == "processing"
    assert created_state.state["context"]["variables"]["count"] == 42
    assert created_state.state["metadata"]["flags"] == ["debug", "verbose"]
    print("✅ CREATE operation successful with complex state data")

    # Test GET operation by ID
    retrieved_state = await state_repo.get(id=state_id)
    assert retrieved_state.id == state_id
    assert retrieved_state.state == state_data
    print("✅ GET by ID operation successful")

    # Test custom get_by_task_and_agent method
    retrieved_by_combo = await state_repo.get_by_task_and_agent(task_id, agent_id)
    assert retrieved_by_combo is not None
    assert retrieved_by_combo.id == state_id
    assert retrieved_by_combo.state["current_step"] == "processing"
    print("✅ GET_BY_TASK_AND_AGENT operation successful")

    # Test get_by_task_and_agent with non-existent combination
    fake_task_id = orm_id()
    fake_agent_id = orm_id()
    non_existent = await state_repo.get_by_task_and_agent(fake_task_id, fake_agent_id)
    assert non_existent is None
    print("✅ GET_BY_TASK_AND_AGENT with non-existent combination returns None")

    # Test UPDATE operation with state progression
    updated_state_data = {
        "current_step": "completed",
        "context": {
            "user_input": "Hello world",
            "variables": {"name": "test", "count": 42, "result": "success"},
        },
        "history": [
            {"step": "init", "timestamp": "2024-01-01T00:00:00Z"},
            {"step": "validate", "timestamp": "2024-01-01T00:01:00Z"},
            {"step": "process", "timestamp": "2024-01-01T00:02:00Z"},
            {"step": "complete", "timestamp": "2024-01-01T00:03:00Z"},
        ],
        "metadata": {
            "version": "1.0",
            "environment": "test",
            "flags": ["debug", "verbose"],
            "duration_ms": 3000,
        },
    }

    updated_state = StateEntity(
        id=state_id,
        task_id=task_id,
        agent_id=agent_id,
        state=updated_state_data,
    )

    result_state = await state_repo.update(updated_state)
    assert result_state.state["current_step"] == "completed"
    assert result_state.state["context"]["variables"]["result"] == "success"
    assert len(result_state.state["history"]) == 4
    assert result_state.state["metadata"]["duration_ms"] == 3000
    print("✅ UPDATE operation successful with state progression")

    # Verify custom method still works after update
    updated_retrieved = await state_repo.get_by_task_and_agent(task_id, agent_id)
    assert updated_retrieved.state["current_step"] == "completed"
    print("✅ GET_BY_TASK_AND_AGENT works after UPDATE")

    # Test LIST operation
    all_states = await state_repo.list()
    assert len(all_states) >= 1
    state_ids = [s.id for s in all_states]
    assert state_id in state_ids
    print("✅ LIST operation successful")

    # Create additional states for different task-agent combinations
    task_id_2 = orm_id()
    agent_id_2 = orm_id()

    additional_states = []
    combinations = [
        (task_id, agent_id_2),  # Same task, different agent
        (task_id_2, agent_id),  # Different task, same agent
        (task_id_2, agent_id_2),  # Both different
    ]

    for i, (t_id, a_id) in enumerate(combinations):
        state = StateEntity(
            id=orm_id(),
            task_id=t_id,
            agent_id=a_id,
            state={
                "current_step": f"step_{i}",
                "data": {
                    "index": i,
                    "combination": f"task_{t_id[:8]}_agent_{a_id[:8]}",
                },
            },
        )
        created = await state_repo.create(state)
        additional_states.append(created)

    print("✅ Additional states created for combination testing")

    # Test LIST with filters
    task_states = await state_repo.list(filters={"task_id": task_id})
    assert len(task_states) == 2  # Original + one additional
    task_state_agents = [s.agent_id for s in task_states]
    assert agent_id in task_state_agents
    assert agent_id_2 in task_state_agents
    print("✅ LIST with task_id filter successful")

    # Test LIST with agent_id filter
    agent_states = await state_repo.list(filters={"agent_id": agent_id})
    assert len(agent_states) == 2  # Original + one additional
    agent_state_tasks = [s.task_id for s in agent_states]
    assert task_id in agent_state_tasks
    assert task_id_2 in agent_state_tasks
    print("✅ LIST with agent_id filter successful")

    # Test unique task-agent combinations with get_by_task_and_agent
    for i, (t_id, a_id) in enumerate(combinations):
        combo_state = await state_repo.get_by_task_and_agent(t_id, a_id)
        assert combo_state is not None
        assert combo_state.task_id == t_id
        assert combo_state.agent_id == a_id
        assert combo_state.state["current_step"] == f"step_{i}"
    print("✅ Unique task-agent combinations verified")

    # Test DELETE operation
    await state_repo.delete(additional_states[0].id)

    # Verify deletion
    all_states_after_delete = await state_repo.list()
    state_ids_after_delete = [s.id for s in all_states_after_delete]
    assert additional_states[0].id not in state_ids_after_delete
    print("✅ DELETE operation successful")

    # Test complex state data preservation
    final_states = await state_repo.list()
    for state in final_states:
        assert isinstance(state.state, dict)
        assert state.id is not None
        assert state.task_id is not None
        assert state.agent_id is not None
    print("✅ Complex state data preservation verified")

    print("✅ Test isolation provided by session-scoped PostgreSQL container")
    print("🎉 ALL TASK STATE POSTGRES REPOSITORY TESTS PASSED!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_state_postgres_repository_unique_constraint(postgres_url):
    """Test that the unique constraint on (task_id, agent_id) is enforced."""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Setup database
    engine = create_async_engine(sqlalchemy_asyncpg_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    state_repo = TaskStatePostgresRepository(async_session_maker, async_session_maker)

    # Create first state
    task_id = orm_id()
    agent_id = orm_id()

    state1 = StateEntity(
        id=orm_id(),
        task_id=task_id,
        agent_id=agent_id,
        state={"version": 1},
    )
    await state_repo.create(state1)
    print("✅ First state created")

    # Attempt to create duplicate (same task_id + agent_id)
    state2 = StateEntity(
        id=orm_id(),  # Different ID
        task_id=task_id,  # Same task_id
        agent_id=agent_id,  # Same agent_id
        state={"version": 2},
    )

    from src.adapters.crud_store.exceptions import DuplicateItemError

    with pytest.raises(DuplicateItemError):
        await state_repo.create(state2)

    print("✅ Unique constraint enforced - duplicate rejected")
    print("🎉 UNIQUE CONSTRAINT TEST PASSED!")
