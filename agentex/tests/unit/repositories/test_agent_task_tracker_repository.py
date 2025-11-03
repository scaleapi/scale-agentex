import asyncio

# Import the repository and entities we need to test
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.adapters.orm import BaseORM
from src.api.schemas.task_messages import TextContent
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.task_messages import (
    MessageAuthor,
    TaskMessageContentType,
)
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.agent_task_tracker_repository import (
    AgentTaskTrackerRepository,
)
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_repository import TaskRepository
from src.utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_agent_task_tracker_repository_crud_operations(postgres_url):
    """Test AgentTaskTrackerRepository CRUD operations with row locking and cursor validation"""

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
    tracker_repo = AgentTaskTrackerRepository(async_session_maker)
    agent_repo = AgentRepository(async_session_maker)
    task_repo = TaskRepository(async_session_maker)
    event_repo = EventRepository(async_session_maker)

    # First, create prerequisites: Agent and Task
    agent_id = orm_id()
    agent = AgentEntity(
        id=agent_id,
        name="test-agent-for-tracker",
        description="Test agent for tracker repository testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.AGENTIC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for tracker testing: {created_agent.id}")

    task_id = orm_id()
    task = TaskEntity(
        id=task_id,
        name="test-task-for-tracker",
        status=TaskStatus.RUNNING,
        status_reason="Task is running for tracker testing",
    )

    # Note: TaskRepository.create() automatically creates an AgentTaskTracker
    created_task = await task_repo.create(agent_id, task)
    print(f"✅ Task created for tracker testing: {created_task.id}")

    # The task creation should have automatically created an AgentTaskTracker
    # Let's find it and test our operations
    all_trackers = await tracker_repo.list()
    assert (
        len(all_trackers) >= 1
    ), "Task creation should have created an AgentTaskTracker"

    # Find our tracker
    our_tracker = None
    for tracker in all_trackers:
        if tracker.agent_id == agent_id and tracker.task_id == task_id:
            our_tracker = tracker
            break

    assert our_tracker is not None, "Could not find the automatically created tracker"
    tracker_id = our_tracker.id
    print(f"✅ Found automatically created tracker: {tracker_id}")

    # Test GET operation
    retrieved_tracker = await tracker_repo.get(id=tracker_id)
    assert retrieved_tracker.id == tracker_id
    assert retrieved_tracker.agent_id == agent_id
    assert retrieved_tracker.task_id == task_id
    assert retrieved_tracker.created_at is not None
    print("✅ GET operation successful")

    # Create some events to test cursor management
    event_id_1 = orm_id()
    created_event_1 = await event_repo.create(
        id=event_id_1,
        task_id=task_id,
        agent_id=agent_id,
        content=TextContent(
            type=TaskMessageContentType.TEXT,
            author=MessageAuthor.AGENT,
            content="First event for tracker testing",
        ),
    )
    print(f"✅ Event 1 created: {event_id_1} (sequence: {created_event_1.sequence_id})")

    event_id_2 = orm_id()
    created_event_2 = await event_repo.create(
        id=event_id_2,
        task_id=task_id,
        agent_id=agent_id,
        content=TextContent(
            type=TaskMessageContentType.TEXT,
            author=MessageAuthor.USER,
            content="Second event for tracker testing",
        ),
    )
    print(f"✅ Event 2 created: {event_id_2} (sequence: {created_event_2.sequence_id})")

    # Test update_agent_task_tracker with cursor advancement
    updated_tracker_1 = await tracker_repo.update_agent_task_tracker(
        id=tracker_id,
        status="processing",
        status_reason="Started processing events",
        last_processed_event_id=event_id_1,
    )

    assert updated_tracker_1.id == tracker_id
    assert updated_tracker_1.status == "processing"
    assert updated_tracker_1.status_reason == "Started processing events"
    assert updated_tracker_1.last_processed_event_id == event_id_1
    assert updated_tracker_1.updated_at is not None
    assert updated_tracker_1.updated_at > updated_tracker_1.created_at
    print("✅ UPDATE with cursor advancement successful")

    # Test cursor advancement to second event
    updated_tracker_2 = await tracker_repo.update_agent_task_tracker(
        id=tracker_id,
        status="processing",
        status_reason="Processed second event",
        last_processed_event_id=event_id_2,
    )

    assert updated_tracker_2.last_processed_event_id == event_id_2
    assert updated_tracker_2.updated_at > updated_tracker_1.updated_at
    print("✅ UPDATE with cursor advancement to second event successful")

    # Test status update without cursor change
    updated_tracker_3 = await tracker_repo.update_agent_task_tracker(
        id=tracker_id,
        status="completed",
        status_reason="All events processed",
        last_processed_event_id=None,  # No cursor change
    )

    assert updated_tracker_3.status == "completed"
    assert updated_tracker_3.status_reason == "All events processed"
    assert (
        updated_tracker_3.last_processed_event_id == event_id_2
    )  # Should remain the same
    print("✅ UPDATE without cursor change successful")

    # Test backward cursor movement prevention
    try:
        await tracker_repo.update_agent_task_tracker(
            id=tracker_id,
            status="error",
            status_reason="Trying to move backwards",
            last_processed_event_id=event_id_1,  # This should fail
        )
        raise AssertionError("Backward cursor movement should have been prevented")
    except ValueError as e:
        assert "Cannot move cursor backwards" in str(e)
        print("✅ Backward cursor movement correctly prevented")

    # Test invalid event ID handling
    try:
        fake_event_id = orm_id()
        await tracker_repo.update_agent_task_tracker(
            id=tracker_id,
            status="error",
            status_reason="Invalid event",
            last_processed_event_id=fake_event_id,
        )
        raise AssertionError("Invalid event ID should have been rejected")
    except ValueError as e:
        assert "not found" in str(e)
        print("✅ Invalid event ID correctly rejected")

    # Test LIST operation
    all_trackers_final = await tracker_repo.list()
    assert len(all_trackers_final) >= 1
    tracker_ids = [t.id for t in all_trackers_final]
    assert tracker_id in tracker_ids
    print("✅ LIST operation successful")

    # Test DELETE operation
    await tracker_repo.delete(tracker_id)

    # Verify deletion
    all_trackers_after_delete = await tracker_repo.list()
    tracker_ids_after_delete = [t.id for t in all_trackers_after_delete]
    assert tracker_id not in tracker_ids_after_delete
    print("✅ DELETE operation successful")

    # Test foreign key relationships work properly
    # All remaining trackers should have valid agent_id and task_id
    for tracker in all_trackers_after_delete:
        assert tracker.agent_id is not None
        assert tracker.task_id is not None
    print("✅ Foreign key relationships verified")

    # NOTE: Each repository operation auto-commits (correct for production)
    # The session-scoped PostgreSQL container provides isolation between test runs
    print("✅ Test isolation provided by session-scoped PostgreSQL container")
    print("🎉 ALL AGENT TASK TRACKER REPOSITORY TESTS PASSED!")
