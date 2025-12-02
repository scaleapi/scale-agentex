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

    @pytest_asyncio.fixture
    async def test_pagination_messages(self, isolated_repositories, test_task):
        """Create a test message using the repository"""
        message_repo = isolated_repositories["task_message_repository"]
        messages = []
        for i in range(60):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=test_task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"Test message content {i}"
                ),
                streaming_status="DONE",
            )
            messages.append(await message_repo.create(message))
        return messages

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

    async def test_list_messages_pagination(
        self, isolated_client, test_pagination_messages, test_task
    ):
        """Test GET /messages/ endpoint with pagination."""
        # Given - A message record exists
        # (created by test_pagination_messages fixture)

        # When - List all messages with pagination
        response = await isolated_client.get(
            "/messages", params={"task_id": test_task.id}
        )
        assert response.status_code == 200
        response_data = response.json()
        # Default limit if none specified
        assert len(response_data) == 50

        page_number = 1
        paginated_messages = []
        while True:
            response = await isolated_client.get(
                "/messages",
                params={
                    "limit": 7,
                    "page_number": page_number,
                    "task_id": test_task.id,
                },
            )
            assert response.status_code == 200
            messages_data = response.json()
            paginated_messages.extend(messages_data)
            if len(messages_data) < 1:
                break
            page_number += 1
        assert len(paginated_messages) == len(test_pagination_messages)
        assert {(d["id"], d["content"]["content"]) for d in paginated_messages} == {
            (d.id, d.content.content) for d in test_pagination_messages
        }

    async def test_list_messages_with_order_by(
        self, isolated_client, isolated_repositories
    ):
        """Test that list messages endpoint supports order_by parameter"""
        # Given - Create an agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="order-by-message-agent",
            description="Agent for order_by message testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="order-by-message-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for order_by message testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create multiple messages
        message_repo = isolated_repositories["task_message_repository"]
        messages = []
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"Order test message {i}"
                ),
                streaming_status="DONE",
            )
            messages.append(await message_repo.create(message))

        # When - Request messages with order_by=created_at and order_direction=asc
        response_asc = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "order_by": "created_at",
                "order_direction": "asc",
            },
        )

        # Then - Should return messages in ascending order
        assert response_asc.status_code == 200
        messages_asc = response_asc.json()
        assert len(messages_asc) == 3

        # Verify ascending order
        for i in range(len(messages_asc) - 1):
            assert messages_asc[i]["created_at"] <= messages_asc[i + 1]["created_at"]

        # When - Request messages with order_by=created_at and order_direction=desc
        response_desc = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "order_by": "created_at",
                "order_direction": "desc",
            },
        )

        # Then - Should return messages in descending order
        assert response_desc.status_code == 200
        messages_desc = response_desc.json()
        assert len(messages_desc) == 3

        # Verify descending order
        for i in range(len(messages_desc) - 1):
            assert messages_desc[i]["created_at"] >= messages_desc[i + 1]["created_at"]

        # Verify asc and desc return different orderings (first element of asc should be in last position of desc)
        # Note: We only check the first element reversal since items with identical timestamps
        # may have unpredictable relative ordering
        assert messages_asc[0]["id"] == messages_desc[-1]["id"]

    async def test_list_messages_order_by_defaults_to_desc(
        self, isolated_client, isolated_repositories
    ):
        """Test that order_direction defaults to desc for messages (newest first)"""
        # Given - Create an agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="order-default-message-agent",
            description="Agent for order default message testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="order-default-message-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for order default message testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create multiple messages
        message_repo = isolated_repositories["task_message_repository"]
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"Default order message {i}"
                ),
                streaming_status="DONE",
            )
            await message_repo.create(message)

        # When - Request messages without specifying order_direction
        response = await isolated_client.get(
            "/messages",
            params={"task_id": task.id},
        )

        # Then - Should return messages successfully
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 3

        # Verify descending order - items with same timestamp may have any relative order,
        # so we only check that timestamps are non-increasing (allowing equal timestamps)
        timestamps = [m["created_at"] for m in messages]
        # Sort timestamps descending and verify the returned order matches a valid descending order
        assert timestamps == sorted(timestamps, reverse=True)
