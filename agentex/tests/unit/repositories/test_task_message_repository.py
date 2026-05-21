# Import the repository and entities we need to test

from datetime import UTC, datetime, timedelta

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.task_messages import DataContent
from src.domain.entities.task_messages import (
    MessageAuthor,
    MessageStyle,
    TaskMessageContentType,
    TaskMessageEntity,
    TextContentEntity,
    TextFormat,
)
from src.utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_message_repository_crud_operations(task_message_repository):
    """Test task message repository CRUD operations using a real database"""
    repo = task_message_repository

    # Create test task
    task_id = orm_id()

    # Create text content
    text_content = TextContentEntity(
        type=TaskMessageContentType.TEXT,
        content="This is a **test message** with markdown formatting",
        author=MessageAuthor.USER,
        style=MessageStyle.STATIC,
        format=TextFormat.MARKDOWN,
    )

    # Create a task message
    task_message = TaskMessageEntity(
        task_id=task_id,
        content=text_content,
        streaming_status="IN_PROGRESS",
    )

    # Test Create
    created_message = await repo.create(task_message)

    assert created_message.id is not None
    assert created_message.task_id == task_id
    assert (
        created_message.content.content
        == "This is a **test message** with markdown formatting"
    )
    assert created_message.streaming_status == "IN_PROGRESS"
    assert created_message.created_at is not None
    assert created_message.updated_at is not None

    message_id = created_message.id

    # Test Read
    retrieved_message = await repo.get(id=message_id)
    assert retrieved_message is not None
    assert retrieved_message.id == message_id
    assert retrieved_message.task_id == task_id
    assert (
        retrieved_message.content.content
        == "This is a **test message** with markdown formatting"
    )

    # Test Read by task_id
    messages_by_task = await repo.find_by_field(
        field_name="task_id", field_value=task_id
    )
    assert len(messages_by_task) == 1
    retrieved_message = messages_by_task[0]
    assert retrieved_message.id == message_id
    assert retrieved_message.task_id == task_id
    assert (
        retrieved_message.content.content
        == "This is a **test message** with markdown formatting"
    )
    assert retrieved_message.streaming_status == "IN_PROGRESS"

    # Test Update
    # Update the streaming status
    retrieved_message.streaming_status = "DONE"
    updated_message = await repo.update(retrieved_message)

    assert updated_message.id == message_id
    result_message = await repo.get(id=message_id)
    assert result_message.streaming_status == "DONE"

    # Test List
    all_messages = await repo.list()
    assert len(all_messages) >= 1
    found = False
    for message in all_messages:
        if message.id == message_id:
            found = True
            break
    assert found

    # Test Delete
    await repo.delete(id=message_id)

    # Test that the item was deleted - MongoDB repository raises exception for missing items
    try:
        await repo.get(id=message_id)
        raise AssertionError("Expected ItemDoesNotExist exception")
    except ItemDoesNotExist:
        pass  # This is expected


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_message_repository_with_data_content(task_message_repository):
    """Test task message repository with data content"""
    repo = task_message_repository

    task_id = orm_id()

    # Create data content using schema object for now (this needs proper entity conversion)
    data_content = DataContent(
        data={
            "type": "chart",
            "values": [1, 2, 3, 4, 5],
            "labels": ["A", "B", "C", "D", "E"],
        },
        author=MessageAuthor.AGENT,
        style=MessageStyle.ACTIVE,
    )

    # Create a task message with data content
    task_message = TaskMessageEntity(
        task_id=task_id,
        content=data_content,
        streaming_status="DONE",
    )

    # Test Create
    created_message = await repo.create(task_message)

    assert created_message.id is not None
    assert created_message.task_id == task_id
    assert created_message.content.data == {
        "type": "chart",
        "values": [1, 2, 3, 4, 5],
        "labels": ["A", "B", "C", "D", "E"],
    }

    # Cleanup
    await repo.delete(id=created_message.id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_task_message_repository_list_by_task_id_pagination(
    task_message_repository,
):
    """Test task message repository list by task_id with pagination"""
    repo = task_message_repository

    task_id = orm_id()

    # Create multiple task messages
    created_ids = []
    for i in range(5):
        text_content = TextContentEntity(
            type=TaskMessageContentType.TEXT,
            content=f"Message {i}",
            author=MessageAuthor.USER,
            style=MessageStyle.STATIC,
            format=TextFormat.PLAIN,
        )

        task_message = TaskMessageEntity(
            task_id=task_id,
            content=text_content,
            streaming_status="DONE",
        )

        created_message = await repo.create(task_message)
        created_ids.append(created_message.id)

    # Test pagination - MongoDB repository doesn't have pagination, so just test finding all
    all_messages = await repo.find_by_field(field_name="task_id", field_value=task_id)
    assert len(all_messages) == 5

    # Cleanup
    for message_id in created_ids:
        await repo.delete(id=message_id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_preserves_caller_supplied_timestamps(
    task_message_repository,
):
    """The Mongo adapter must respect caller-supplied created_at/updated_at and
    not clobber them with datetime.now(UTC) at insert time. This is the
    server-side fix for the cross-request race that flipped message ordering
    in the UI when two messages.create calls arrived within milliseconds."""
    repo = task_message_repository
    task_id = orm_id()

    caller_time = datetime(2025, 4, 1, 8, 30, 0, tzinfo=UTC)
    text_content = TextContentEntity(
        type=TaskMessageContentType.TEXT,
        content="caller-stamped",
        author=MessageAuthor.USER,
        style=MessageStyle.STATIC,
        format=TextFormat.PLAIN,
    )
    task_message = TaskMessageEntity(
        task_id=task_id,
        content=text_content,
        streaming_status="DONE",
        created_at=caller_time,
        updated_at=caller_time,
    )

    # pymongo strips tzinfo on read (BSON Date stores UTC but returns naive
    # datetimes by default), so compare against the naive UTC equivalent.
    expected_naive = caller_time.replace(tzinfo=None)

    created = await repo.create(task_message)
    assert created.created_at.replace(tzinfo=None) == expected_naive
    assert created.updated_at.replace(tzinfo=None) == expected_naive

    fetched = await repo.get(id=created.id)
    assert fetched.created_at.replace(tzinfo=None) == expected_naive
    assert fetched.updated_at.replace(tzinfo=None) == expected_naive

    await repo.delete(id=created.id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_batch_create_preserves_per_item_timestamps(
    task_message_repository,
):
    """batch_create must preserve per-item caller-supplied timestamps so that
    the service-layer microsecond/millisecond stagger is durable in storage."""
    repo = task_message_repository
    task_id = orm_id()

    base = datetime(2025, 4, 2, 12, 0, 0, tzinfo=UTC)
    messages = [
        TaskMessageEntity(
            task_id=task_id,
            content=TextContentEntity(
                type=TaskMessageContentType.TEXT,
                content=f"msg-{i}",
                author=MessageAuthor.USER,
                style=MessageStyle.STATIC,
                format=TextFormat.PLAIN,
            ),
            streaming_status="DONE",
            # Insert with timestamps in *descending* order to prove that the
            # adapter is not assigning a single now() to all items.
            created_at=base + timedelta(milliseconds=10 - i),
            updated_at=base + timedelta(milliseconds=10 - i),
        )
        for i in range(3)
    ]

    created = await repo.batch_create(messages)
    assert len(created) == 3
    for i, c in enumerate(created):
        expected = (base + timedelta(milliseconds=10 - i)).replace(tzinfo=None)
        assert c.created_at.replace(tzinfo=None) == expected
        assert c.updated_at.replace(tzinfo=None) == expected

    # Cleanup
    for c in created:
        await repo.delete(id=c.id)
