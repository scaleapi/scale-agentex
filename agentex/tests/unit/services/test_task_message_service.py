from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.task_messages import TextContent
from src.domain.entities.task_messages import MessageAuthor, TaskMessageEntity
from src.domain.repositories.task_message_repository import TaskMessageRepository
from src.domain.services.task_message_service import TaskMessageService

# UTC timezone constant
UTC = ZoneInfo("UTC")


@pytest.fixture
def task_message_repository(mongodb_database):
    """Real TaskMessageRepository using test MongoDB database"""
    return TaskMessageRepository(mongodb_database)


@pytest.fixture
def task_message_service(task_message_repository, redis_stream_repository):
    """Create TaskMessageService instance with real repository"""
    return TaskMessageService(
        message_repository=task_message_repository,
        stream_repository=redis_stream_repository,
    )


@pytest.fixture
def sample_task_id():
    """Sample task ID for testing"""
    return str(uuid4())


@pytest.fixture
def sample_message_content():
    """Sample message content for testing"""
    return TextContent(
        content="Hello, this is a test message", author=MessageAuthor.USER
    )


@pytest.fixture
def sample_task_message(sample_task_id, sample_message_content):
    """Sample task message entity for testing"""
    return TaskMessageEntity(
        id=str(uuid4()),
        task_id=sample_task_id,
        content=sample_message_content,
        streaming_status="DONE",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_task_messages(sample_task_id):
    """Multiple sample task messages for testing"""
    base_time = datetime.now(UTC)
    messages = []

    for i in range(3):
        message = TaskMessageEntity(
            id=str(uuid4()),
            task_id=sample_task_id,
            content=TextContent(content=f"Message {i + 1}", author=MessageAuthor.USER),
            streaming_status="DONE",
            created_at=base_time + timedelta(seconds=i),
            updated_at=base_time + timedelta(seconds=i),
        )
        messages.append(message)

    return messages


@pytest.mark.unit
@pytest.mark.asyncio
class TestTaskMessageService:
    """Test suite for TaskMessageService"""

    async def test_get_message_success(
        self,
        task_message_service,
        task_message_repository,
        sample_task_id,
        sample_message_content,
    ):
        """Test successful message retrieval by ID"""
        # Given - Create a real message in the database
        created_message = await task_message_service.append_message(
            task_id=sample_task_id,
            content=sample_message_content,
            streaming_status="DONE",
        )

        # When
        result = await task_message_service.get_message(created_message.id)

        # Then
        assert result is not None
        assert result.id == created_message.id
        assert result.task_id == sample_task_id
        assert result.content.content == sample_message_content.content

    async def test_get_message_not_found(
        self, task_message_service, task_message_repository
    ):
        """Test getting a non-existent message raises ItemDoesNotExist."""
        non_existent_id = "507f1f77bcf86cd799439013"

        with pytest.raises(ItemDoesNotExist):
            await task_message_service.get_message(non_existent_id)

    async def test_get_messages_success(self, task_message_service, sample_task_id):
        """Test successful retrieval of all messages for a task"""
        # Given - Create multiple messages for the task
        contents = [
            TextContent(content="First message", author=MessageAuthor.USER),
            TextContent(content="Second message", author=MessageAuthor.AGENT),
            TextContent(content="Third message", author=MessageAuthor.USER),
        ]

        created_messages = []
        for content in contents:
            message = await task_message_service.append_message(
                task_id=sample_task_id,
                content=content,
                streaming_status="DONE",
            )
            created_messages.append(message)

        # When
        result = await task_message_service.get_messages(
            sample_task_id, limit=100, page_number=1, order_direction="asc"
        )

        # Then
        assert len(result) == 3
        # Messages should be sorted by created_at (oldest first)
        for i, message in enumerate(result):
            assert message.task_id == sample_task_id
            assert message.content.content == contents[i].content

    async def test_get_messages_with_limit(self, task_message_service, sample_task_id):
        """Test message retrieval with limit"""
        # Given - Create multiple messages
        contents = [
            TextContent(content="Message 1", author=MessageAuthor.USER),
            TextContent(content="Message 2", author=MessageAuthor.AGENT),
            TextContent(content="Message 3", author=MessageAuthor.USER),
        ]

        for content in contents:
            await task_message_service.append_message(
                task_id=sample_task_id, content=content
            )

        # When
        result = await task_message_service.get_messages(
            sample_task_id, limit=2, page_number=1, order_direction="asc"
        )

        # Then
        assert len(result) == 2
        assert result[0].content.content == "Message 1"
        assert result[1].content.content == "Message 2"

    async def test_append_message_success(
        self, task_message_service, sample_task_id, sample_message_content
    ):
        """Test successful message append"""
        # When
        result = await task_message_service.append_message(
            task_id=sample_task_id,
            content=sample_message_content,
            streaming_status="IN_PROGRESS",
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.task_id == sample_task_id
        assert result.content.content == sample_message_content.content
        assert result.streaming_status == "IN_PROGRESS"
        assert result.created_at is not None

    async def test_append_message_without_streaming_status(
        self, task_message_service, sample_task_id, sample_message_content
    ):
        """Test message append without streaming status"""
        # When
        result = await task_message_service.append_message(
            task_id=sample_task_id, content=sample_message_content
        )

        # Then
        assert result is not None
        assert result.task_id == sample_task_id
        assert result.content.content == sample_message_content.content
        assert result.streaming_status is None

    async def test_append_messages_batch_success(
        self, task_message_service, sample_task_id
    ):
        """Test successful batch message append with time increments"""
        # Given
        contents = [
            TextContent(content="Message 1", author=MessageAuthor.USER),
            TextContent(content="Message 2", author=MessageAuthor.AGENT),
            TextContent(content="Message 3", author=MessageAuthor.USER),
        ]

        # When
        result = await task_message_service.append_messages(
            task_id=sample_task_id, contents=contents
        )

        # Then
        assert len(result) == 3

        # Check that all messages were created correctly
        for i, message in enumerate(result):
            assert message.id is not None
            assert message.task_id == sample_task_id
            assert message.content.content == contents[i].content
            assert message.created_at is not None

            # Check that timestamps are incremented (or at least not decreasing)
            if i > 0:
                # Later messages should have timestamps >= previous (microsecond precision may be identical)
                assert message.created_at >= result[i - 1].created_at

    async def test_update_message_success(
        self, task_message_service, sample_task_id, sample_message_content
    ):
        """Test successful message update"""
        # Given - Create a message first
        original_message = await task_message_service.append_message(
            task_id=sample_task_id,
            content=sample_message_content,
            streaming_status="IN_PROGRESS",
        )

        new_content = TextContent(content="Updated message", author=MessageAuthor.AGENT)

        # When
        result = await task_message_service.update_message(
            task_id=sample_task_id,
            message_id=original_message.id,
            content=new_content,
            streaming_status="DONE",
        )

        # Then
        assert result is not None
        assert result.id == original_message.id
        assert result.task_id == sample_task_id
        assert result.content.content == "Updated message"
        assert result.streaming_status == "DONE"

    async def test_update_message_wrong_task_id(
        self, task_message_service, sample_task_id, sample_message_content
    ):
        """Test message update fails when message belongs to different task"""
        # Given - Create a message in one task
        original_message = await task_message_service.append_message(
            task_id=sample_task_id,
            content=sample_message_content,
            streaming_status="IN_PROGRESS",
        )

        # Try to update with wrong task ID
        wrong_task_id = str(uuid4())
        new_content = TextContent(content="Updated message", author=MessageAuthor.AGENT)

        # When
        result = await task_message_service.update_message(
            task_id=wrong_task_id,
            message_id=original_message.id,
            content=new_content,
            streaming_status="DONE",
        )

        # Then
        assert result is None

    async def test_update_message_not_found(self, task_message_service, sample_task_id):
        """Test message update when message doesn't exist raises ItemDoesNotExist"""
        # Given
        non_existent_id = "507f1f77bcf86cd799439013"  # Valid ObjectId format
        new_content = TextContent(content="Updated message", author=MessageAuthor.AGENT)

        # When/Then
        with pytest.raises(ItemDoesNotExist):
            await task_message_service.update_message(
                task_id=sample_task_id,
                message_id=non_existent_id,
                content=new_content,
                streaming_status="DONE",
            )

    async def test_update_messages_batch_success(
        self, task_message_service, sample_task_id
    ):
        """Test successful batch message updates"""
        # Given - Create multiple messages first
        message1 = await task_message_service.append_message(
            task_id=sample_task_id,
            content=TextContent(
                content="Original message 1", author=MessageAuthor.USER
            ),
            streaming_status="IN_PROGRESS",
        )
        message2 = await task_message_service.append_message(
            task_id=sample_task_id,
            content=TextContent(
                content="Original message 2", author=MessageAuthor.AGENT
            ),
            streaming_status="IN_PROGRESS",
        )

        # Prepare updates
        updates = {
            message1.id: TextContent(
                content="Updated message 1", author=MessageAuthor.AGENT
            ),
            message2.id: TextContent(
                content="Updated message 2", author=MessageAuthor.USER
            ),
        }

        # When
        result = await task_message_service.update_messages(sample_task_id, updates)

        # Then
        assert len(result) == 2

        # Verify the updates were applied correctly
        for updated_message in result:
            if updated_message.id == message1.id:
                assert updated_message.content.content == "Updated message 1"
                assert updated_message.content.author == MessageAuthor.AGENT
            elif updated_message.id == message2.id:
                assert updated_message.content.content == "Updated message 2"
                assert updated_message.content.author == MessageAuthor.USER

    async def test_delete_message_success(
        self, task_message_service, sample_task_id, sample_message_content
    ):
        """Test successful message deletion"""
        # Given - Create a message first
        created_message = await task_message_service.append_message(
            task_id=sample_task_id,
            content=sample_message_content,
            streaming_status="DONE",
        )

        # When
        result = await task_message_service.delete_message(
            sample_task_id, created_message.id
        )

        # Then
        assert result is True

    async def test_delete_message_wrong_task_id(
        self, task_message_service, sample_task_id, sample_message_content
    ):
        """Test message deletion fails when message belongs to different task"""
        # Given - Create a message in one task
        created_message = await task_message_service.append_message(
            task_id=sample_task_id,
            content=sample_message_content,
            streaming_status="DONE",
        )

        # Try to delete with wrong task ID
        wrong_task_id = str(uuid4())

        # When
        result = await task_message_service.delete_message(
            wrong_task_id, created_message.id
        )

        # Then
        assert result is False

    async def test_delete_message_not_found(
        self, task_message_service, task_message_repository, sample_task_id
    ):
        """Test message deletion when message doesn't exist raises ItemDoesNotExist"""
        # Given
        non_existent_id = "507f1f77bcf86cd799439013"

        # When/Then
        with pytest.raises(ItemDoesNotExist):
            await task_message_service.delete_message(sample_task_id, non_existent_id)

    async def test_delete_messages_batch_success(
        self, task_message_service, task_message_repository, sample_task_id
    ):
        """Test successful batch message deletion"""
        # Given - Create real messages in the database first
        contents = [
            TextContent(content="Message 1", author=MessageAuthor.USER),
            TextContent(content="Message 2", author=MessageAuthor.AGENT),
        ]
        created_messages = []
        for content in contents:
            message = await task_message_service.append_message(
                task_id=sample_task_id,
                content=content,
                streaming_status="DONE",
            )
            created_messages.append(message)

        message_ids = [msg.id for msg in created_messages]

        # When
        result = await task_message_service.delete_messages(sample_task_id, message_ids)

        # Then
        assert result == 2  # Number of messages deleted

        # Verify messages are actually deleted
        for message_id in message_ids:
            with pytest.raises(ItemDoesNotExist):
                await task_message_service.get_message(message_id)

    async def test_delete_messages_partial_success(
        self, task_message_service, task_message_repository, sample_task_id
    ):
        """Test batch deletion with some messages belonging to wrong task"""
        # Given - Create a valid message for the correct task
        valid_content = TextContent(content="Valid message", author=MessageAuthor.USER)
        valid_message = await task_message_service.append_message(
            task_id=sample_task_id,
            content=valid_content,
            streaming_status="DONE",
        )

        # Create a message for a different task
        wrong_task_id = str(uuid4())
        invalid_content = TextContent(
            content="Wrong task message", author=MessageAuthor.USER
        )
        invalid_message = await task_message_service.append_message(
            task_id=wrong_task_id,
            content=invalid_content,
            streaming_status="DONE",
        )

        message_ids = [valid_message.id, invalid_message.id]

        # When
        result = await task_message_service.delete_messages(sample_task_id, message_ids)

        # Then
        assert result == 1  # Only one valid message deleted

        # Valid message should be deleted
        with pytest.raises(ItemDoesNotExist):
            await task_message_service.get_message(valid_message.id)

        # Invalid message should still exist
        retrieved_invalid = await task_message_service.get_message(invalid_message.id)
        assert retrieved_invalid.id == invalid_message.id

    async def test_delete_all_messages_success(
        self, task_message_service, task_message_repository, sample_task_id
    ):
        """Test successful deletion of all messages for a task"""
        # Given - Create real messages in the database first
        contents = [
            TextContent(content="Message 1", author=MessageAuthor.USER),
            TextContent(content="Message 2", author=MessageAuthor.AGENT),
            TextContent(content="Message 3", author=MessageAuthor.USER),
            TextContent(content="Message 4", author=MessageAuthor.AGENT),
            TextContent(content="Message 5", author=MessageAuthor.USER),
        ]
        created_messages = []
        for content in contents:
            message = await task_message_service.append_message(
                task_id=sample_task_id,
                content=content,
                streaming_status="DONE",
            )
            created_messages.append(message)

        # When
        result = await task_message_service.delete_all_messages(sample_task_id)

        # Then
        assert result == 5  # Number of messages deleted

        # Verify all messages are deleted
        for message in created_messages:
            with pytest.raises(ItemDoesNotExist):
                await task_message_service.get_message(message.id)

    async def test_delete_all_messages_no_messages(
        self, task_message_service, task_message_repository, sample_task_id
    ):
        """Test deletion of all messages when no messages exist"""
        # Given - no messages exist for this task (clean database)

        # When
        result = await task_message_service.delete_all_messages(sample_task_id)

        # Then
        assert result == 0  # No messages to delete
