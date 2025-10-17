# Import the repository and entities we need to test

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
