import os

# Import the repository and entities we need to test
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from domain.entities.states import StateEntity
from domain.repositories.task_state_repository import TaskStateRepository
from utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_state_repository_crud_operations(mongodb_database):
    """Test TaskStateRepository CRUD operations with MongoDB and custom query methods"""

    # Create repository with MongoDB database
    state_repo = TaskStateRepository(mongodb_database)

    # Test CREATE operation with complex state data
    task_id = orm_id()
    agent_id = orm_id()

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
        id=None,  # Let MongoDB auto-generate
        task_id=task_id,
        agent_id=agent_id,
        state=state_data,
    )

    created_state = await state_repo.create(state)
    assert created_state.id is not None
    assert created_state.task_id == task_id
    assert created_state.agent_id == agent_id
    assert created_state.state["current_step"] == "processing"
    assert created_state.state["context"]["variables"]["count"] == 42
    assert created_state.state["metadata"]["flags"] == ["debug", "verbose"]
    assert created_state.created_at is not None
    assert created_state.updated_at is not None
    print("✅ CREATE operation successful with complex state data")

    # Test custom get_by_task_and_agent method
    retrieved_state = await state_repo.get_by_task_and_agent(task_id, agent_id)
    assert retrieved_state is not None
    assert retrieved_state.id == created_state.id
    assert retrieved_state.state["current_step"] == "processing"
    assert retrieved_state.state["history"] == state_data["history"]
    print("✅ GET_BY_TASK_AND_AGENT operation successful")

    # Test get_by_task_and_agent with non-existent combination
    fake_task_id = orm_id()
    fake_agent_id = orm_id()
    non_existent = await state_repo.get_by_task_and_agent(fake_task_id, fake_agent_id)
    assert non_existent is None
    print("✅ GET_BY_TASK_AND_AGENT with non-existent combination returns None")

    # Test GET operation by ID
    retrieved_by_id = await state_repo.get(id=created_state.id)
    assert retrieved_by_id.id == created_state.id
    assert retrieved_by_id.state == state_data
    print("✅ GET by ID operation successful")

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
        id=created_state.id,
        task_id=task_id,
        agent_id=agent_id,
        state=updated_state_data,
    )

    result_state = await state_repo.update(updated_state)
    assert result_state.state["current_step"] == "completed"
    assert result_state.state["context"]["variables"]["result"] == "success"
    assert len(result_state.state["history"]) == 4
    assert result_state.state["metadata"]["duration_ms"] == 3000
    assert result_state.updated_at is not None
    # Note: In MongoDB, created_at might not be returned in updates, but updated_at should be set
    print("✅ UPDATE operation successful with state progression")

    # Verify custom method still works after update
    updated_retrieved = await state_repo.get_by_task_and_agent(task_id, agent_id)
    assert updated_retrieved.state["current_step"] == "completed"
    print("✅ GET_BY_TASK_AND_AGENT works after UPDATE")

    # Test LIST operation
    all_states = await state_repo.list()
    assert len(all_states) >= 1
    state_ids = [s.id for s in all_states]
    assert created_state.id in state_ids
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
            id=None,
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

    # Test find_by_field with task_id
    task_states = await state_repo.find_by_field("task_id", task_id)
    assert len(task_states) == 2  # Original + one additional
    task_state_agents = [s.agent_id for s in task_states]
    assert agent_id in task_state_agents
    assert agent_id_2 in task_state_agents
    print("✅ FIND_BY_FIELD by task_id successful")

    # Test find_by_field with agent_id
    agent_states = await state_repo.find_by_field("agent_id", agent_id)
    assert len(agent_states) == 2  # Original + one additional
    agent_state_tasks = [s.task_id for s in agent_states]
    assert task_id in agent_state_tasks
    assert task_id_2 in agent_state_tasks
    print("✅ FIND_BY_FIELD by agent_id successful")

    # Test unique task-agent combinations with get_by_task_and_agent
    for i, (t_id, a_id) in enumerate(combinations):
        combo_state = await state_repo.get_by_task_and_agent(t_id, a_id)
        assert combo_state is not None
        assert combo_state.task_id == t_id
        assert combo_state.agent_id == a_id
        assert combo_state.state["current_step"] == f"step_{i}"
    print("✅ Unique task-agent combinations verified")

    # Test BATCH operations
    batch_states = []
    for i in range(3):
        state = StateEntity(
            id=None,
            task_id=orm_id(),
            agent_id=orm_id(),
            state={
                "batch_index": i,
                "data": {"value": f"batch_item_{i}"},
                "config": {"enabled": True, "priority": i + 1},
            },
        )
        batch_states.append(state)

    created_batch = await state_repo.batch_create(batch_states)
    assert len(created_batch) == 3
    assert all(s.id is not None for s in created_batch)
    print("✅ BATCH_CREATE operation successful")

    # Test DELETE operation
    await state_repo.delete(id=additional_states[0].id)

    # Verify deletion
    all_states_after_delete = await state_repo.list()
    state_ids_after_delete = [s.id for s in all_states_after_delete]
    assert additional_states[0].id not in state_ids_after_delete
    print("✅ DELETE operation successful")

    # Test delete_by_field with task_id
    deleted_count = await state_repo.delete_by_field("task_id", task_id_2)
    assert deleted_count >= 1  # Should delete states for task_id_2
    print(f"✅ DELETE_BY_FIELD operation successful (deleted {deleted_count} states)")

    # Test complex state data preservation
    final_states = await state_repo.list()
    for state in final_states:
        assert isinstance(state.state, dict)
        assert state.id is not None
        assert state.task_id is not None
        assert state.agent_id is not None
        # Note: MongoDB may not return created_at for updated documents, but updated_at should exist
        assert state.updated_at is not None
    print("✅ Complex state data preservation verified")

    # Test MongoDB ObjectId handling
    for state in final_states:
        assert isinstance(state.id, str)  # Should be converted from ObjectId to string
        assert len(state.id) == 24  # MongoDB ObjectId string length
    print("✅ MongoDB ObjectId handling verified")

    print("✅ Test isolation provided by function-scoped MongoDB database")
    print("🎉 ALL TASK STATE REPOSITORY TESTS PASSED!")
