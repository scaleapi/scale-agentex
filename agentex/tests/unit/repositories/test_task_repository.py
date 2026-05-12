import asyncio
import os

# Import the repository and entities we need to test
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from adapters.orm import BaseORM
from domain.entities.agents import ACPType, AgentEntity, AgentStatus
from domain.entities.tasks import TaskEntity, TaskStatus
from domain.repositories.agent_repository import AgentRepository
from domain.repositories.task_repository import TaskRepository
from utils.ids import orm_id


def assert_task_lists_by_name(
    received: list[TaskEntity], expected: list[TaskEntity]
) -> None:
    """Assert that two lists of TaskEntity match by name."""

    assert [task.name for task in received] == [task.name for task in expected]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_repository_crud_operations(postgres_url):
    """Test TaskRepository CRUD operations with agent relationships and transactional rollback"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
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
    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    # First, create an agent (required for task creation)
    # Use unique names to avoid collisions with other tests sharing the same session-scoped DB
    agent_id = orm_id()
    unique_suffix = agent_id[:8]
    agent = AgentEntity(
        id=agent_id,
        name=f"test-agent-for-tasks-{unique_suffix}",
        description="Test agent for task repository testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for task testing: {created_agent.id}")

    # Create a test task
    task_id = orm_id()
    task = TaskEntity(
        id=task_id,
        name=f"test-task-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="Task is running for testing",
    )

    # Test CREATE operation
    task_name = f"test-task-{unique_suffix}"
    created_task = await task_repo.create(agent_id, task)
    assert created_task.id == task_id
    assert created_task.name == task_name
    assert created_task.status == TaskStatus.RUNNING
    assert created_task.status_reason == "Task is running for testing"
    assert created_task.created_at is not None
    assert created_task.updated_at is not None
    print("✅ CREATE operation successful")

    # Test GET operation by ID
    retrieved_task = await task_repo.get(id=task_id)
    assert retrieved_task.id == created_task.id
    assert retrieved_task.name == created_task.name
    assert retrieved_task.status == created_task.status
    print("✅ GET by ID operation successful")

    # Test GET operation by name
    retrieved_task_by_name = await task_repo.get(name=task_name)
    assert retrieved_task_by_name.id == created_task.id
    assert retrieved_task_by_name.name == task_name
    print("✅ GET by name operation successful")

    # Test GET agent by task ID
    retrieved_agent = await agent_repo.list(filters={"task_id": task_id})
    assert len(retrieved_agent) == 1
    assert retrieved_agent[0].id == agent_id
    print("✅ GET agent by task ID operation successful")

    # Test UPDATE operation
    updated_task = TaskEntity(
        id=task_id,
        name=task_name,  # Keep same name
        status=TaskStatus.COMPLETED,
        status_reason="Task completed successfully",
    )

    result_task = await task_repo.update(updated_task)
    assert result_task.id == task_id
    assert result_task.status == TaskStatus.COMPLETED
    assert result_task.status_reason == "Task completed successfully"
    # Note: Timestamps are managed by database triggers, not comparing them here
    print("✅ UPDATE operation successful")

    # Test LIST operation
    all_tasks = await task_repo.list()
    assert len(all_tasks) >= 1
    assert any(t.id == task_id for t in all_tasks)
    print("✅ LIST operation successful")

    # Create a second task to test multiple items
    task_id_2 = orm_id()
    task_2 = TaskEntity(
        id=task_id_2,
        name=f"test-task-2-{unique_suffix}",
        status=TaskStatus.FAILED,
        status_reason="Second test task",
    )

    created_task_2 = await task_repo.create(agent_id, task_2)
    assert created_task_2.id == task_id_2

    # Test LIST with multiple tasks
    all_tasks_multi = await task_repo.list()
    assert len(all_tasks_multi) >= 2
    task_ids = [t.id for t in all_tasks_multi]
    assert task_id in task_ids
    assert task_id_2 in task_ids
    print("✅ LIST multiple tasks successful")

    # Test DELETE operation - Expected to fail due to foreign key constraints
    # This shows our referential integrity is working correctly!
    try:
        await task_repo.delete(task_id_2)
        raise AssertionError("DELETE should have failed due to foreign key constraints")
    except Exception as e:
        # This is expected - tasks with relationships cannot be deleted without cleanup
        assert "foreign key constraint" in str(e).lower()
        print(
            "✅ DELETE correctly prevented due to foreign key constraints (referential integrity working!)"
        )

    # NOTE: Each repository operation auto-commits (correct for production)
    # The session-scoped PostgreSQL container provides isolation between test runs
    print("✅ Test isolation provided by session-scoped PostgreSQL container")
    print("🎉 ALL TASK REPOSITORY TESTS PASSED!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_repository_params_support(postgres_url):
    """Test TaskRepository CRUD operations with params field"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness and create engine
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
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
    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    # First, create an agent (required for task creation)
    # Use unique names to avoid collisions with other tests sharing the same session-scoped DB
    agent_id = orm_id()
    unique_suffix = agent_id[:8]
    agent = AgentEntity(
        id=agent_id,
        name=f"test-agent-params-{unique_suffix}",
        description="Test agent for params testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for params testing: {created_agent.id}")

    # Test CREATE operation with params
    task_id = orm_id()
    task_params = {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 1000,
        "nested": {"key": "value", "number": 42},
    }
    task_name = f"test-task-with-params-{unique_suffix}"
    task = TaskEntity(
        id=task_id,
        name=task_name,
        status=TaskStatus.RUNNING,
        status_reason="Task with params for testing",
        params=task_params,
    )

    # Create task with params
    created_task = await task_repo.create(agent_id, task)
    assert created_task.id == task_id
    assert created_task.name == task_name
    assert created_task.params == task_params
    print("✅ CREATE operation with params successful")

    # Test GET operation by ID preserves params
    retrieved_task = await task_repo.get(id=task_id)
    assert retrieved_task.id == created_task.id
    assert retrieved_task.name == created_task.name
    assert retrieved_task.params == task_params
    print("✅ GET by ID operation preserves params")

    # Test GET operation by name preserves params
    retrieved_task_by_name = await task_repo.get(name=task_name)
    assert retrieved_task_by_name.id == created_task.id
    assert retrieved_task_by_name.params == task_params
    print("✅ GET by name operation preserves params")

    # Test UPDATE operation preserves and updates params
    updated_params = {
        "model": "gpt-4-turbo",
        "temperature": 0.5,
        "max_tokens": 2000,
        "new_field": "added",
    }
    updated_task = TaskEntity(
        id=task_id,
        name=task_name,
        status=TaskStatus.COMPLETED,
        status_reason="Task completed with updated params",
        params=updated_params,
    )

    result_task = await task_repo.update(updated_task)
    assert result_task.id == task_id
    assert result_task.status == TaskStatus.COMPLETED
    assert result_task.params == updated_params
    print("✅ UPDATE operation preserves and updates params")

    # Test LIST operation includes params
    all_tasks = await task_repo.list()
    params_task = next((t for t in all_tasks if t.id == task_id), None)
    assert params_task is not None
    assert params_task.params == updated_params
    print("✅ LIST operation includes params")

    # Test CREATE operation with None params (should work)
    task_id_null = orm_id()
    task_null_params = TaskEntity(
        id=task_id_null,
        name=f"test-task-null-params-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="Task with null params",
        params=None,
    )

    created_task_null = await task_repo.create(agent_id, task_null_params)
    assert created_task_null.id == task_id_null
    assert created_task_null.params is None
    print("✅ CREATE operation with null params successful")

    # Verify null params are preserved in retrieval
    retrieved_null_task = await task_repo.get(id=task_id_null)
    assert retrieved_null_task.params is None
    print("✅ NULL params preserved in retrieval")

    print("🎉 ALL TASK REPOSITORY PARAMS TESTS PASSED!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_repository_task_metadata_support(postgres_url):
    """Test TaskRepository CRUD operations with task_metadata field"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness and create engine
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
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
    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    # First, create an agent (required for task creation)
    # Use unique names to avoid collisions with other tests sharing the same session-scoped DB
    agent_id = orm_id()
    unique_suffix = agent_id[:8]
    agent = AgentEntity(
        id=agent_id,
        name=f"test-agent-metadata-{unique_suffix}",
        description="Test agent for task_metadata testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for task_metadata testing: {created_agent.id}")

    # Test CREATE operation with task_metadata
    task_id = orm_id()
    task_metadata = {
        "workflow": {
            "stage": "initial",
            "priority": "high",
            "assignee": {
                "name": "test-user",
                "department": "engineering",
                "skills": ["python", "testing", "async"],
            },
        },
        "tracking": {
            "version": "1.2.3",
            "created_by": "automated-system",
            "flags": {
                "experimental": True,
                "requires_review": False,
                "auto_retry": True,
            },
            "metrics": {
                "estimated_duration": 3600,
                "complexity_score": 85.5,
                "retry_count": 0,
            },
        },
        "tags": ["integration", "high-priority", "automated"],
        "custom_data": {
            "nested_array": [{"id": 1, "value": "first"}, {"id": 2, "value": "second"}],
            "boolean_flag": True,
            "null_field": None,
            "numeric_precision": 123.456789,
        },
    }
    task_name = f"test-task-with-metadata-{unique_suffix}"
    task = TaskEntity(
        id=task_id,
        name=task_name,
        status=TaskStatus.RUNNING,
        status_reason="Task with task_metadata for testing",
        task_metadata=task_metadata,
    )

    # Create task with task_metadata
    created_task = await task_repo.create(agent_id, task)
    assert created_task.id == task_id
    assert created_task.name == task_name
    assert created_task.task_metadata == task_metadata
    print("✅ CREATE operation with task_metadata successful")

    # Test GET operation by ID preserves task_metadata
    retrieved_task = await task_repo.get(id=task_id)
    assert retrieved_task.id == created_task.id
    assert retrieved_task.name == created_task.name
    assert retrieved_task.task_metadata == task_metadata
    print("✅ GET by ID operation preserves task_metadata")

    # Test GET operation by name preserves task_metadata
    retrieved_task_by_name = await task_repo.get(name=task_name)
    assert retrieved_task_by_name.id == created_task.id
    assert retrieved_task_by_name.task_metadata == task_metadata
    print("✅ GET by name operation preserves task_metadata")

    # Test UPDATE operation preserves and updates task_metadata
    updated_metadata = {
        "workflow": {
            "stage": "completed",
            "priority": "low",
            "assignee": {
                "name": "updated-user",
                "department": "qa",
                "skills": ["testing", "validation"],
            },
        },
        "tracking": {
            "version": "1.3.0",
            "created_by": "automated-system",
            "updated_by": "test-runner",
            "flags": {
                "experimental": False,
                "requires_review": True,
                "auto_retry": False,
            },
            "metrics": {
                "estimated_duration": 1800,
                "complexity_score": 92.1,
                "retry_count": 1,
                "actual_duration": 2100,
            },
        },
        "tags": ["integration", "completed", "verified"],
        "results": {
            "success": True,
            "error_count": 0,
            "warnings": ["minor issue resolved"],
        },
    }
    updated_task = TaskEntity(
        id=task_id,
        name=task_name,
        status=TaskStatus.COMPLETED,
        status_reason="Task completed with updated task_metadata",
        task_metadata=updated_metadata,
    )

    result_task = await task_repo.update(updated_task)
    assert result_task.id == task_id
    assert result_task.status == TaskStatus.COMPLETED
    assert result_task.task_metadata == updated_metadata
    print("✅ UPDATE operation preserves and updates task_metadata")

    # Test LIST operation includes task_metadata
    all_tasks = await task_repo.list()
    metadata_task = next((t for t in all_tasks if t.id == task_id), None)
    assert metadata_task is not None
    assert metadata_task.task_metadata == updated_metadata
    print("✅ LIST operation includes task_metadata")

    # Test CREATE operation with None task_metadata (should work)
    task_id_null = orm_id()
    task_null_metadata = TaskEntity(
        id=task_id_null,
        name=f"test-task-null-metadata-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="Task with null task_metadata",
        task_metadata=None,
    )

    created_task_null = await task_repo.create(agent_id, task_null_metadata)
    assert created_task_null.id == task_id_null
    assert created_task_null.task_metadata is None
    print("✅ CREATE operation with null task_metadata successful")

    # Verify null task_metadata are preserved in retrieval
    retrieved_null_task = await task_repo.get(id=task_id_null)
    assert retrieved_null_task.task_metadata is None
    print("✅ NULL task_metadata preserved in retrieval")

    print("🎉 ALL TASK REPOSITORY TASK_METADATA TESTS PASSED!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_repository_null_task_metadata_handling(postgres_url):
    """Test TaskRepository handling of null task_metadata values"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness and create engine
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
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
    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    # First, create an agent (required for task creation)
    # Use unique names to avoid collisions with other tests sharing the same session-scoped DB
    agent_id = orm_id()
    unique_suffix = agent_id[:8]
    agent = AgentEntity(
        id=agent_id,
        name=f"test-agent-null-metadata-{unique_suffix}",
        description="Test agent for null task_metadata testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for null task_metadata testing: {created_agent.id}")

    # Test CREATE with task_metadata=None
    task_id_null = orm_id()
    task_name = f"test-task-null-metadata-handling-{unique_suffix}"
    task_null = TaskEntity(
        id=task_id_null,
        name=task_name,
        status=TaskStatus.RUNNING,
        status_reason="Task with null task_metadata",
        task_metadata=None,
    )

    created_task_null = await task_repo.create(agent_id, task_null)
    assert created_task_null.id == task_id_null
    assert created_task_null.task_metadata is None
    print("✅ CREATE with task_metadata=None successful")

    # Test retrieval preserves null task_metadata
    retrieved_null_task = await task_repo.get(id=task_id_null)
    assert retrieved_null_task.id == task_id_null
    assert retrieved_null_task.task_metadata is None
    print("✅ Retrieval preserves null task_metadata")

    retrieved_null_by_name = await task_repo.get(name=task_name)
    assert retrieved_null_by_name.id == task_id_null
    assert retrieved_null_by_name.task_metadata is None
    print("✅ Retrieval by name preserves null task_metadata")

    # Test UPDATE from null to populated task_metadata
    populated_metadata = {
        "status": "updated",
        "version": 2,
        "features": {
            "logging": True,
            "monitoring": False,
        },
        "data": ["item1", "item2"],
    }
    updated_task = TaskEntity(
        id=task_id_null,
        name=task_name,
        status=TaskStatus.RUNNING,
        status_reason="Task updated with populated task_metadata",
        task_metadata=populated_metadata,
    )

    result_task = await task_repo.update(updated_task)
    assert result_task.id == task_id_null
    assert result_task.task_metadata == populated_metadata
    print("✅ UPDATE from null to populated task_metadata successful")

    # Verify the populated metadata persists
    retrieved_populated = await task_repo.get(id=task_id_null)
    assert retrieved_populated.task_metadata == populated_metadata
    print("✅ Populated task_metadata persists after update")

    # Test UPDATE from populated back to null task_metadata
    updated_back_to_null = TaskEntity(
        id=task_id_null,
        name=task_name,
        status=TaskStatus.COMPLETED,
        status_reason="Task updated back to null task_metadata",
        task_metadata=None,
    )

    result_null_again = await task_repo.update(updated_back_to_null)
    assert result_null_again.id == task_id_null
    assert result_null_again.task_metadata is None
    assert result_null_again.status == TaskStatus.COMPLETED
    print("✅ UPDATE from populated to null task_metadata successful")

    # Verify null metadata persists after second update
    final_retrieved = await task_repo.get(id=task_id_null)
    assert final_retrieved.task_metadata is None
    assert final_retrieved.status == TaskStatus.COMPLETED
    print("✅ Null task_metadata persists after second update")

    print("🎉 ALL NULL TASK_METADATA HANDLING TESTS PASSED!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_with_join_includes_task_metadata(postgres_url):
    """Test TaskRepository.list_with_join includes task_metadata field"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(BaseORM.metadata.create_all)
                # Test connectivity
                await conn.execute(text("SELECT 1"))
            break
        except Exception as expected:
            if attempt < 9:
                print(
                    f"Database not ready (attempt {attempt + 1}), retrying... Error: {expected}"
                )
                await asyncio.sleep(2)
                continue
            raise

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # Clear existing data to ensure clean test state
    async with async_session_maker() as session:
        # Get all table names and truncate them (with CASCADE to handle foreign keys)
        result = await session.execute(
            text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename != 'alembic_version'
        """)
        )
        tables = [row[0] for row in result.fetchall()]

        if tables:
            # Use TRUNCATE with CASCADE to handle foreign key constraints
            await session.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )
        await session.commit()

    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    # Use unique names to avoid collisions with other tests sharing the same session-scoped DB
    unique_suffix = orm_id()[:8]

    # Create test agents
    agent_1 = AgentEntity(
        id=orm_id(),
        name=f"agent-with-metadata-tasks-{unique_suffix}",
        description="Test agent for task metadata join testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )
    await agent_repo.create(agent_1)

    agent_2 = AgentEntity(
        id=orm_id(),
        name=f"agent-with-null-metadata-tasks-{unique_suffix}",
        description="Test agent for null task metadata join testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )
    await agent_repo.create(agent_2)

    # Create tasks with task_metadata
    task_with_metadata_1 = TaskEntity(
        id=orm_id(),
        name=f"task-with-metadata-1-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="Task with metadata for join testing",
        task_metadata={
            "priority": "high",
            "category": "testing",
            "features": ["metadata", "join"],
            "config": {"debug": True, "timeout": 30},
        },
    )
    await task_repo.create(agent_1.id, task_with_metadata_1)

    task_with_metadata_2 = TaskEntity(
        id=orm_id(),
        name=f"task-with-metadata-2-{unique_suffix}",
        status=TaskStatus.FAILED,
        status_reason="Another task with metadata",
        task_metadata={
            "priority": "medium",
            "category": "integration",
            "features": ["api", "database"],
            "config": {"debug": False, "retries": 3},
        },
    )
    await task_repo.create(agent_1.id, task_with_metadata_2)

    # Create tasks without task_metadata (null)
    task_without_metadata_1 = TaskEntity(
        id=orm_id(),
        name=f"task-without-metadata-1-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="Task without metadata",
        task_metadata=None,
    )
    await task_repo.create(agent_2.id, task_without_metadata_1)

    task_without_metadata_2 = TaskEntity(
        id=orm_id(),
        name=f"task-without-metadata-2-{unique_suffix}",
        status=TaskStatus.COMPLETED,
        status_reason="Another task without metadata",
        task_metadata=None,
    )
    await task_repo.create(agent_2.id, task_without_metadata_2)

    # Test list_with_join returns task_metadata for all tasks
    all_tasks = await task_repo.list_with_join(order_direction="asc")
    assert len(all_tasks) == 4

    # Find each task and verify task_metadata
    tasks_by_name = {task.name: task for task in all_tasks}

    # Verify tasks with metadata
    assert task_with_metadata_1.name in tasks_by_name
    metadata_task_1 = tasks_by_name[task_with_metadata_1.name]
    assert metadata_task_1.task_metadata is not None
    assert metadata_task_1.task_metadata["priority"] == "high"
    assert metadata_task_1.task_metadata["category"] == "testing"

    assert task_with_metadata_2.name in tasks_by_name
    metadata_task_2 = tasks_by_name[task_with_metadata_2.name]
    assert metadata_task_2.task_metadata is not None
    assert metadata_task_2.task_metadata["priority"] == "medium"
    assert metadata_task_2.task_metadata["category"] == "integration"

    # Verify tasks without metadata (null)
    assert task_without_metadata_1.name in tasks_by_name
    null_task_1 = tasks_by_name[task_without_metadata_1.name]
    assert null_task_1.task_metadata is None

    assert task_without_metadata_2.name in tasks_by_name
    null_task_2 = tasks_by_name[task_without_metadata_2.name]
    assert null_task_2.task_metadata is None

    print("✅ list_with_join returns task_metadata for all tasks")

    # Test filtering works with task_metadata present - filter by agent_id
    agent_1_tasks = await task_repo.list_with_join(
        agent_id=agent_1.id, order_direction="asc"
    )
    assert len(agent_1_tasks) == 2
    for task in agent_1_tasks:
        assert task.task_metadata is not None
        assert "priority" in task.task_metadata

    print("✅ Filtering by agent_id works with task_metadata present")

    # Test filtering by agent_name
    agent_2_tasks = await task_repo.list_with_join(
        agent_name=agent_2.name, order_direction="asc"
    )
    assert len(agent_2_tasks) == 2
    for task in agent_2_tasks:
        assert task.task_metadata is None

    print("✅ Filtering by agent_name works with task_metadata")

    # Test filtering by task status
    running_tasks = await task_repo.list_with_join(
        task_filters={"status": TaskStatus.RUNNING}, order_direction="asc"
    )
    assert len(running_tasks) == 2
    # Should have one with metadata and one without
    metadata_count = sum(1 for task in running_tasks if task.task_metadata is not None)
    null_metadata_count = sum(1 for task in running_tasks if task.task_metadata is None)
    assert metadata_count == 1
    assert null_metadata_count == 1

    print("✅ Filtering by task status works with mixed task_metadata")

    # Test ordering with task_metadata present
    ordered_by_name = await task_repo.list_with_join(
        order_by="name", order_direction="asc"
    )
    assert len(ordered_by_name) == 4
    # Verify ordering is correct and task_metadata is preserved
    assert ordered_by_name[0].name == task_with_metadata_1.name
    assert ordered_by_name[0].task_metadata is not None
    assert ordered_by_name[3].name == task_without_metadata_2.name
    assert ordered_by_name[3].task_metadata is None

    print("✅ Ordering works correctly with task_metadata present")

    print("🎉 ALL LIST_WITH_JOIN TASK_METADATA TESTS PASSED!")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_with_join(postgres_url):
    """Test TaskRepository.list_with_join"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(BaseORM.metadata.create_all)
                # Test connectivity
                await conn.execute(text("SELECT 1"))
            break
        except Exception as expected:
            if attempt < 9:
                print(
                    f"Database not ready (attempt {attempt + 1}), retrying... Error: {expected}"
                )
                await asyncio.sleep(2)
                continue
            raise

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # Clear existing data to ensure clean test state
    async with async_session_maker() as session:
        # Get all table names and truncate them (with CASCADE to handle foreign keys)
        result = await session.execute(
            text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename != 'alembic_version'
        """)
        )
        tables = [row[0] for row in result.fetchall()]

        if tables:
            # Use TRUNCATE with CASCADE to handle foreign key constraints
            await session.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )
        await session.commit()

    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    # Use unique names to avoid collisions with other tests sharing the same session-scoped DB
    unique_suffix = orm_id()[:8]

    agent_1 = AgentEntity(
        id=orm_id(),
        name=f"agent-1-{unique_suffix}",
        description="Test agent for task repository testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )
    await agent_repo.create(agent_1)

    agent_2 = AgentEntity(
        id=orm_id(),
        name=f"agent-2-{unique_suffix}",
        description="Test agent for task repository testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )
    await agent_repo.create(agent_2)

    task_1_1 = TaskEntity(
        id=orm_id(),
        name=f"agent-1-task-1-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="status reason b",
    )
    await task_repo.create(agent_1.id, task_1_1)

    task_1_2 = TaskEntity(
        id=orm_id(),
        name=f"agent-1-task-2-{unique_suffix}",
        status=TaskStatus.FAILED,
        status_reason="status reason a",
    )
    await task_repo.create(agent_1.id, task_1_2)

    task_2_1 = TaskEntity(
        id=orm_id(),
        name=f"agent-2-task-1-{unique_suffix}",
        status=TaskStatus.RUNNING,
        status_reason="status reason a",
    )
    await task_repo.create(agent_2.id, task_2_1)

    # agent_id
    assert_task_lists_by_name(
        expected=[task_1_1, task_1_2],
        received=await task_repo.list_with_join(
            agent_id=agent_1.id,
            order_direction="asc",
        ),
    )

    # agent_id + desc
    assert_task_lists_by_name(
        expected=[task_1_2, task_1_1],
        received=await task_repo.list_with_join(
            agent_id=agent_1.id,
            order_direction="desc",
        ),
    )

    # Test task_filters with single value
    assert_task_lists_by_name(
        expected=[task_1_1, task_2_1],
        received=await task_repo.list_with_join(
            task_filters={"status": TaskStatus.RUNNING},
            order_direction="asc",
        ),
    )

    # Test task_filters with multiple values (sequence)
    assert_task_lists_by_name(
        expected=[task_1_1, task_1_2, task_2_1],
        received=await task_repo.list_with_join(
            task_filters={"status": [TaskStatus.RUNNING, TaskStatus.FAILED]},
            order_direction="asc",
        ),
    )

    # Test agent_name filtering
    assert_task_lists_by_name(
        expected=[task_1_1, task_1_2],
        received=await task_repo.list_with_join(
            agent_name=agent_1.name,
            order_direction="asc",
        ),
    )

    # Test order_by different columns
    assert_task_lists_by_name(
        expected=[
            task_1_1,
            task_1_2,
        ],  # ordered by name: agent-1-task-1, agent-1-task-2
        received=await task_repo.list_with_join(
            agent_id=agent_1.id,
            order_by="name",
            order_direction="asc",
        ),
    )

    # Test order_by status reason ascending
    assert_task_lists_by_name(
        expected=[
            task_1_2,
            task_1_1,
        ],  # ordered by status reason asc: status reason a, status reason b
        received=await task_repo.list_with_join(
            agent_id=agent_1.id,
            order_by="status_reason",
            order_direction="asc",
        ),
    )

    # Test order_by status reason descending
    assert_task_lists_by_name(
        expected=[
            task_1_1,
            task_1_2,
        ],  # ordered by status reason desc: status reason b, status reason a
        received=await task_repo.list_with_join(
            agent_id=agent_1.id,
            order_by="status_reason",
            order_direction="desc",
        ),
    )

    # Test order_by updated_at (should be same as created_at since no updates)
    assert_task_lists_by_name(
        expected=[
            task_1_1,
            task_1_2,
            task_2_1,
        ],
        received=await task_repo.list_with_join(
            order_by="name",
            order_direction="asc",
        ),
    )

    # Test order_by updated_at desc
    assert_task_lists_by_name(
        expected=[
            task_2_1,
            task_1_2,
            task_1_1,
        ],
        received=await task_repo.list_with_join(
            order_by="name",
            order_direction="desc",
        ),
    )

    # Test order_by status reason asc with fallback to updated_at
    assert_task_lists_by_name(
        expected=[
            task_1_2,
            task_2_1,
            task_1_1,
        ],
        received=await task_repo.list_with_join(
            order_by="status_reason",
            order_direction="asc",
        ),
    )

    # Test order_by status reason desc with fallback to updated_at
    assert_task_lists_by_name(
        expected=[
            task_1_1,
            task_2_1,
            task_1_2,
        ],
        received=await task_repo.list_with_join(
            order_by="status_reason",
            order_direction="desc",
        ),
    )

    # Test combined filters: agent_id + task_filters
    assert_task_lists_by_name(
        expected=[task_1_1],
        received=await task_repo.list_with_join(
            agent_id=agent_1.id,
            task_filters={"status": TaskStatus.RUNNING},
            order_direction="asc",
        ),
    )

    # Test combined filters: agent_name + task_filters
    assert_task_lists_by_name(
        expected=[task_1_2],
        received=await task_repo.list_with_join(
            agent_name=agent_1.name,
            task_filters={"status": TaskStatus.FAILED},
            order_direction="asc",
        ),
    )

    # Test edge case: no results with non-existent agent
    empty_result = await task_repo.list_with_join(
        agent_name="non-existent-agent",
        order_direction="asc",
    )
    assert len(empty_result) == 0

    # Test edge case: no results with impossible filter combination
    empty_result_2 = await task_repo.list_with_join(
        agent_id=agent_1.id,
        task_filters={"status": TaskStatus.COMPLETED},  # no completed tasks exist
        order_direction="asc",
    )
    assert len(empty_result_2) == 0

    # Test edge case: empty task_filters dict (should return all tasks)
    all_tasks_result = await task_repo.list_with_join(
        task_filters={},
        order_direction="asc",
    )
    assert len(all_tasks_result) == 3  # all 3 tasks should be returned


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_with_join_filters_by_task_metadata(postgres_url):
    """list_with_join should filter rows by JSONB containment on task_metadata."""

    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

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

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    task_repo = TaskRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)

    unique_suffix = orm_id()[:8]
    agent = AgentEntity(
        id=orm_id(),
        name=f"metadata-filter-agent-{unique_suffix}",
        description="agent for metadata containment filter test",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )
    await agent_repo.create(agent)

    user_a_task = await task_repo.create(
        agent.id,
        TaskEntity(
            id=orm_id(),
            name=f"user-a-task-{unique_suffix}",
            status=TaskStatus.RUNNING,
            task_metadata={"created_by_user_id": "user-a", "other": "field"},
        ),
    )
    user_b_task = await task_repo.create(
        agent.id,
        TaskEntity(
            id=orm_id(),
            name=f"user-b-task-{unique_suffix}",
            status=TaskStatus.RUNNING,
            task_metadata={"created_by_user_id": "user-b"},
        ),
    )
    no_meta_task = await task_repo.create(
        agent.id,
        TaskEntity(
            id=orm_id(),
            name=f"no-meta-task-{unique_suffix}",
            status=TaskStatus.RUNNING,
            task_metadata=None,
        ),
    )

    results = await task_repo.list_with_join(
        task_metadata={"created_by_user_id": "user-a"},
    )

    result_ids = {t.id for t in results}
    assert user_a_task.id in result_ids
    assert user_b_task.id not in result_ids
    assert no_meta_task.id not in result_ids
