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
    MessageStyle,
    TaskMessageContentType,
    TextFormat,
)
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_repository import TaskRepository
from src.utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_event_repository_crud_operations(postgres_url):
    """Test EventRepository CRUD operations with foreign key relationships and complex querying"""

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
    event_repo = EventRepository(async_session_maker, async_session_maker)
    agent_repo = AgentRepository(async_session_maker, async_session_maker)
    task_repo = TaskRepository(async_session_maker, async_session_maker)

    # First, create prerequisites: Agent and Task
    agent_id = orm_id()
    agent = AgentEntity(
        id=agent_id,
        name="test-agent-for-events",
        description="Test agent for event repository testing",
        docker_image="test/agent:latest",
        status=AgentStatus.READY,
        acp_url="http://localhost:8000/acp",
        acp_type=ACPType.ASYNC,
    )

    created_agent = await agent_repo.create(agent)
    print(f"✅ Agent created for event testing: {created_agent.id}")

    task_id = orm_id()
    task = TaskEntity(
        id=task_id,
        name="test-task-for-events",
        status=TaskStatus.RUNNING,
        status_reason="Task is running for event testing",
    )

    created_task = await task_repo.create(agent_id, task)
    print(f"✅ Task created for event testing: {created_task.id}")

    # Test CREATE operation with TextContent
    event_id_1 = orm_id()
    text_content = TextContent(
        type=TaskMessageContentType.TEXT,
        author=MessageAuthor.AGENT,
        style=MessageStyle.STATIC,
        format=TextFormat.MARKDOWN,
        content="This is a test event message with **markdown** formatting",
    )

    created_event_1 = await event_repo.create(
        id=event_id_1, task_id=task_id, agent_id=agent_id, content=text_content
    )

    assert created_event_1.id == event_id_1
    assert created_event_1.task_id == task_id
    assert created_event_1.agent_id == agent_id
    assert created_event_1.sequence_id is not None  # Auto-generated
    assert created_event_1.content is not None
    assert created_event_1.content.type == TaskMessageContentType.TEXT
    assert (
        created_event_1.content.content
        == "This is a test event message with **markdown** formatting"
    )
    assert created_event_1.created_at is not None
    print("✅ CREATE operation successful (with TextContent)")

    # Test CREATE operation without content
    event_id_2 = orm_id()
    created_event_2 = await event_repo.create(
        id=event_id_2, task_id=task_id, agent_id=agent_id, content=None
    )

    assert created_event_2.id == event_id_2
    assert created_event_2.content is None
    assert created_event_2.sequence_id > created_event_1.sequence_id  # Should increment
    print("✅ CREATE operation successful (without content)")

    # Test GET operation by ID
    retrieved_event = await event_repo.get(id=event_id_1)
    assert retrieved_event.id == created_event_1.id
    assert retrieved_event.sequence_id == created_event_1.sequence_id
    assert retrieved_event.content.content == text_content.content
    print("✅ GET by ID operation successful")

    # Test LIST operation
    all_events = await event_repo.list()
    assert len(all_events) >= 2
    event_ids = [e.id for e in all_events]
    assert event_id_1 in event_ids
    assert event_id_2 in event_ids
    print("✅ LIST operation successful")

    # Create a third event to test complex querying
    event_id_3 = orm_id()
    await event_repo.create(
        id=event_id_3,
        task_id=task_id,
        agent_id=agent_id,
        content=TextContent(
            type=TaskMessageContentType.TEXT,
            author=MessageAuthor.USER,
            content="Third event for sequence testing",
        ),
    )
    print("✅ Third event created for sequence testing")

    # Test complex querying: list_events_after_last_processed
    # Get all events (no last_processed_event_id)
    all_task_events = await event_repo.list_events_after_last_processed(
        task_id=task_id, agent_id=agent_id
    )
    assert len(all_task_events) == 3
    # Should be ordered by sequence_id
    assert (
        all_task_events[0].sequence_id
        < all_task_events[1].sequence_id
        < all_task_events[2].sequence_id
    )
    print("✅ Complex query: all events successful")

    # Test filtering after a specific event
    events_after_first = await event_repo.list_events_after_last_processed(
        task_id=task_id, agent_id=agent_id, last_processed_event_id=event_id_1
    )
    assert len(events_after_first) == 2
    assert events_after_first[0].id == event_id_2
    assert events_after_first[1].id == event_id_3
    print("✅ Complex query: events after first successful")

    # Test filtering with limit
    events_with_limit = await event_repo.list_events_after_last_processed(
        task_id=task_id, agent_id=agent_id, limit=2
    )
    assert len(events_with_limit) == 2
    assert events_with_limit[0].id == event_id_1  # First in sequence
    assert events_with_limit[1].id == event_id_2  # Second in sequence
    print("✅ Complex query: events with limit successful")

    # Test filtering with both last_processed_event_id and limit
    events_after_with_limit = await event_repo.list_events_after_last_processed(
        task_id=task_id, agent_id=agent_id, last_processed_event_id=event_id_1, limit=1
    )
    assert len(events_after_with_limit) == 1
    assert events_after_with_limit[0].id == event_id_2
    print("✅ Complex query: events after with limit successful")

    # Test DELETE operation (inherited from base)
    await event_repo.delete(event_id_3)

    # Verify deletion
    all_events_after_delete = await event_repo.list()
    event_ids_after_delete = [e.id for e in all_events_after_delete]
    assert event_id_3 not in event_ids_after_delete
    assert event_id_1 in event_ids_after_delete  # Should still exist
    assert event_id_2 in event_ids_after_delete  # Should still exist
    print("✅ DELETE operation successful")

    # Verify complex query still works after deletion
    remaining_events = await event_repo.list_events_after_last_processed(
        task_id=task_id, agent_id=agent_id
    )
    assert len(remaining_events) == 2
    assert remaining_events[0].id == event_id_1
    assert remaining_events[1].id == event_id_2
    print("✅ Complex query works after deletion")

    # Test foreign key relationships work properly
    # Events should be linked to existing task and agent
    assert all(e.task_id == task_id for e in remaining_events)
    assert all(e.agent_id == agent_id for e in remaining_events)
    print("✅ Foreign key relationships verified")

    # NOTE: Each repository operation auto-commits (correct for production)
    # The session-scoped PostgreSQL container provides isolation between test runs
    print("✅ Test isolation provided by session-scoped PostgreSQL container")
    print("🎉 ALL EVENT REPOSITORY TESTS PASSED!")
