"""
Integration tests for messages endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.task_messages import TaskMessageEntity, TextContentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestMessagesAPIIntegration:
    """Integration tests for messages endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for message creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent",
            description="Test agent for message testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task(self, isolated_repositories, test_agent):
        """Create a test task for message creation"""
        task_repo = isolated_repositories["task_repository"]

        task = TaskEntity(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task for message testing",
        )

        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_message(self, isolated_repositories, test_task):
        """Create a test message using the repository"""
        message_repo = isolated_repositories["task_message_repository"]

        content = TextContentEntity(
            type="text", author="user", content="Test message content"
        )

        message = TaskMessageEntity(
            id=orm_id(),
            task_id=test_task.id,
            content=content,
            streaming_status="DONE",
        )

        return await message_repo.create(message)

    async def test_create_message_success_and_retrieve(
        self, isolated_client, test_task
    ):
        """Test creating a message via POST and retrieving it via GET"""
        # Given - Message data
        message_data = {
            "task_id": test_task.id,
            "content": {
                "type": "text",
                "author": "user",
                "content": "Hello, test message!",
            },
            "streaming_status": "DONE",
        }

        # When - Create message via POST
        response = await isolated_client.post("/messages", json=message_data)

        # Then - Should succeed and return created message
        assert response.status_code == 200
        created_message = response.json()

        # Validate response schema
        assert "id" in created_message
        assert created_message["task_id"] == test_task.id
        assert created_message["content"]["type"] == "text"
        assert created_message["content"]["author"] == "user"
        assert created_message["content"]["content"] == "Hello, test message!"
        assert created_message["streaming_status"] == "DONE"

        # When - Retrieve the same message via GET
        message_id = created_message["id"]
        get_response = await isolated_client.get(f"/messages/{message_id}")

        # Then - Should return the same message data
        assert get_response.status_code == 200
        retrieved_message = get_response.json()
        assert retrieved_message["id"] == created_message["id"]
        assert retrieved_message["content"]["content"] == "Hello, test message!"

    #
    async def test_list_messages_returns_valid_structure_and_schema(
        self, isolated_client, test_message, test_task
    ):
        """Test that list messages endpoint returns valid array structure with real data"""
        # When - Request all messages for the task
        response = await isolated_client.get(f"/messages?task_id={test_task.id}")

        # Then - Should succeed with valid list structure and schema
        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)
        assert len(messages) >= 1  # Should have at least our test message

        # Validate message schema for the messages we created
        found_test_message = False
        for message in messages:
            assert "id" in message and isinstance(message["id"], str)
            assert "task_id" in message and isinstance(message["task_id"], str)
            assert "content" in message and isinstance(message["content"], dict)
            assert "streaming_status" in message

            # Check if this is our test message
            if message["id"] == test_message.id:
                found_test_message = True
                assert message["content"]["content"] == "Test message content"
                assert message["streaming_status"] == "DONE"

        assert found_test_message, "Test message should be present in the list"

    async def test_update_message_success_and_retrieve(
        self, isolated_client, test_message, test_task
    ):
        """Test updating a message via PUT and retrieving updated data"""
        # Given - Updated message data
        update_data = {
            "task_id": test_task.id,
            "content": {
                "type": "text",
                "author": "agent",
                "content": "Updated message content",
            },
            "streaming_status": "IN_PROGRESS",
        }

        # When - Update message via PUT
        response = await isolated_client.put(
            f"/messages/{test_message.id}", json=update_data
        )

        # Then - Should succeed and return updated message
        assert response.status_code == 200
        updated_message = response.json()

        # Validate updated fields
        assert updated_message["id"] == test_message.id
        assert updated_message["content"]["type"] == "text"
        assert updated_message["content"]["author"] == "agent"
        assert updated_message["content"]["content"] == "Updated message content"
        assert updated_message["streaming_status"] == "IN_PROGRESS"

        # When - Retrieve the updated message via GET
        get_response = await isolated_client.get(f"/messages/{test_message.id}")

        # Then - Should return the updated data
        assert get_response.status_code == 200
        retrieved_message = get_response.json()
        assert retrieved_message["content"]["content"] == "Updated message content"
        assert retrieved_message["streaming_status"] == "IN_PROGRESS"

    async def test_batch_create_messages_success(self, isolated_client, test_task):
        """Test creating multiple messages via batch POST"""
        # Given - Batch message data
        batch_data = {
            "task_id": test_task.id,
            "contents": [
                {"type": "text", "author": "user", "content": "First batch message"},
                {"type": "text", "author": "agent", "content": "Second batch message"},
            ],
        }

        # When - Create messages via batch POST
        response = await isolated_client.post("/messages/batch", json=batch_data)

        # Then - Should succeed and return created messages
        assert response.status_code == 200
        created_messages = response.json()
        assert isinstance(created_messages, list)
        assert len(created_messages) == 2

        # Validate each message
        assert created_messages[0]["content"]["content"] == "First batch message"
        assert created_messages[1]["content"]["content"] == "Second batch message"
        assert all(msg["task_id"] == test_task.id for msg in created_messages)

        # Update messages via batch PUT
        response = await isolated_client.put(
            "/messages/batch",
            json={
                "task_id": test_task.id,
                "updates": {
                    created_messages[0]["id"]: {
                        "type": "text",
                        "author": "user",
                        "content": "First batch message update",
                    },
                    created_messages[1]["id"]: {
                        "type": "text",
                        "author": "agent",
                        "content": "Second batch message update",
                    },
                },
            },
        )
        assert response.status_code == 200
        updated_messages = response.json()
        assert isinstance(updated_messages, list)
        assert len(updated_messages) == 2
        assert updated_messages[0]["content"]["content"] == "First batch message update"
        assert (
            updated_messages[1]["content"]["content"] == "Second batch message update"
        )
        assert all(msg["task_id"] == test_task.id for msg in updated_messages)

    async def test_get_message_non_existent_returns_404_or_null(self, isolated_client):
        """Test getting a non-existent message"""
        # When - Get a non-existent message
        response = await isolated_client.get("/messages/non-existent-message-id")

        # Then - Should return 404 or null (depending on implementation)
        # Note: The API returns None which becomes null in JSON
        assert response.status_code == 404
        resp_json = response.json()
        assert "Item with id" in resp_json["message"]
