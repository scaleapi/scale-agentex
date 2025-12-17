"""
Integration tests for messages endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.task_messages import (
    DataContentEntity,
    TaskMessageEntity,
    TextContentEntity,
)
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
        """Test that list messages endpoint returns valid list response with real data"""
        # When - Request all messages for the task
        response = await isolated_client.get(f"/messages?task_id={test_task.id}")

        # Then - Should succeed with a list response
        assert response.status_code == 200
        messages = response.json()

        # Original endpoint returns a list directly
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

    async def test_list_messages_paginated(
        self, isolated_client, test_pagination_messages, test_task
    ):
        """Test GET /messages/paginated endpoint with cursor-based pagination."""
        # Given - 60 message records exist (created by test_pagination_messages fixture)

        # When - List messages with default limit using the paginated endpoint
        response = await isolated_client.get(
            "/messages/paginated", params={"task_id": test_task.id}
        )
        assert response.status_code == 200
        response_data = response.json()

        # Validate paginated response structure
        assert "data" in response_data
        assert "next_cursor" in response_data
        assert "has_more" in response_data

        # Default limit is 50, we have 60 messages so has_more should be True
        assert len(response_data["data"]) == 50
        assert response_data["has_more"] is True
        assert response_data["next_cursor"] is not None

        # Test cursor-based pagination - collect all messages
        cursor = None
        paginated_messages = []
        while True:
            params = {"task_id": test_task.id, "limit": 7}
            if cursor:
                params["cursor"] = cursor

            response = await isolated_client.get("/messages/paginated", params=params)
            assert response.status_code == 200
            page_data = response.json()

            paginated_messages.extend(page_data["data"])

            if not page_data["has_more"]:
                break
            cursor = page_data["next_cursor"]

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

        # Then - Should return messages in ascending order (list response)
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

        # Then - Should return messages in descending order (list response)
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

        # Then - Should return messages successfully (list response)
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 3

        # Verify descending order - items with same timestamp may have any relative order,
        # so we only check that timestamps are non-increasing (allowing equal timestamps)
        timestamps = [m["created_at"] for m in messages]
        # Sort timestamps descending and verify the returned order matches a valid descending order
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_list_messages_filter_by_content_type(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering messages by content type"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="filter-test-agent",
            description="Agent for filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="filter-test-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create messages with different content types
        message_repo = isolated_repositories["task_message_repository"]

        # Create text messages
        text_messages = []
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"Text message {i}"
                ),
                streaming_status="DONE",
            )
            text_messages.append(await message_repo.create(message))

        # Create data messages
        data_messages = []
        for i in range(2):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data", author="agent", data={"value": i}
                ),
                streaming_status="DONE",
            )
            data_messages.append(await message_repo.create(message))

        # When - Filter by text content type
        response = await isolated_client.get(
            "/messages",
            params={"task_id": task.id, "filters": '{"content": {"type": "text"}}'},
        )

        # Then - Should return only text messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 3
        assert all(msg["content"]["type"] == "text" for msg in filtered_messages)

        # When - Filter by data content type
        response = await isolated_client.get(
            "/messages",
            params={"task_id": task.id, "filters": '{"content": {"type": "data"}}'},
        )

        # Then - Should return only data messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 2
        assert all(msg["content"]["type"] == "data" for msg in filtered_messages)

    async def test_list_messages_filter_by_author(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering messages by author"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="author-filter-agent",
            description="Agent for author filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="author-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for author filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create messages from different authors
        message_repo = isolated_repositories["task_message_repository"]

        # User messages
        user_messages = []
        for i in range(2):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"User message {i}"
                ),
                streaming_status="DONE",
            )
            user_messages.append(await message_repo.create(message))

        # Agent messages
        agent_messages = []
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="agent", content=f"Agent message {i}"
                ),
                streaming_status="DONE",
            )
            agent_messages.append(await message_repo.create(message))

        # When - Filter by user author
        response = await isolated_client.get(
            "/messages",
            params={"task_id": task.id, "filters": '{"content": {"author": "user"}}'},
        )

        # Then - Should return only user messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 2
        assert all(msg["content"]["author"] == "user" for msg in filtered_messages)

        # When - Filter by agent author
        response = await isolated_client.get(
            "/messages",
            params={"task_id": task.id, "filters": '{"content": {"author": "agent"}}'},
        )

        # Then - Should return only agent messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 3
        assert all(msg["content"]["author"] == "agent" for msg in filtered_messages)

    async def test_list_messages_filter_by_streaming_status(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering messages by streaming status"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="status-filter-agent",
            description="Agent for status filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="status-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for status filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create messages with different streaming statuses
        message_repo = isolated_repositories["task_message_repository"]

        # In progress messages
        in_progress_messages = []
        for i in range(2):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"In progress message {i}"
                ),
                streaming_status="IN_PROGRESS",
            )
            in_progress_messages.append(await message_repo.create(message))

        # Done messages
        done_messages = []
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="agent", content=f"Done message {i}"
                ),
                streaming_status="DONE",
            )
            done_messages.append(await message_repo.create(message))

        # When - Filter by IN_PROGRESS status
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"streaming_status": "IN_PROGRESS"}',
            },
        )

        # Then - Should return only in progress messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 2
        assert all(
            msg["streaming_status"] == "IN_PROGRESS" for msg in filtered_messages
        )

        # When - Filter by DONE status
        response = await isolated_client.get(
            "/messages",
            params={"task_id": task.id, "filters": '{"streaming_status": "DONE"}'},
        )

        # Then - Should return only done messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 3
        assert all(msg["streaming_status"] == "DONE" for msg in filtered_messages)

    async def test_list_messages_filter_combined_criteria(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering messages with multiple criteria"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="combined-filter-agent",
            description="Agent for combined filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="combined-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for combined filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create diverse messages
        message_repo = isolated_repositories["task_message_repository"]

        # Target message: text + user + done
        target_message = TaskMessageEntity(
            id=orm_id(),
            task_id=task.id,
            content=TextContentEntity(
                type="text", author="user", content="Target message"
            ),
            streaming_status="DONE",
        )
        await message_repo.create(target_message)

        # Non-matching messages
        non_matches = [
            TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="agent", content="Wrong author"
                ),
                streaming_status="DONE",
            ),
            TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data", author="user", data={"test": "wrong type"}
                ),
                streaming_status="DONE",
            ),
            TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content="Wrong status"
                ),
                streaming_status="IN_PROGRESS",
            ),
        ]
        for message in non_matches:
            await message_repo.create(message)

        # When - Filter by text + user + done
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"type": "text", "author": "user"}, "streaming_status": "DONE"}',
            },
        )

        # Then - Should return only the target message
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 1
        assert filtered_messages[0]["id"] == target_message.id
        assert filtered_messages[0]["content"]["type"] == "text"
        assert filtered_messages[0]["content"]["author"] == "user"
        assert filtered_messages[0]["streaming_status"] == "DONE"

    async def test_list_messages_filter_data_content_partial_match(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering data messages with partial matching on nested data fields"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="data-filter-agent",
            description="Agent for data content filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="data-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for data content filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create data messages with different nested data
        message_repo = isolated_repositories["task_message_repository"]

        # Messages with status="completed"
        completed_messages = []
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={"status": "completed", "value": i, "extra": "field"},
                ),
                streaming_status="DONE",
            )
            completed_messages.append(await message_repo.create(message))

        # Messages with status="pending"
        pending_messages = []
        for i in range(2):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={"status": "pending", "value": i + 10},
                ),
                streaming_status="DONE",
            )
            pending_messages.append(await message_repo.create(message))

        # Messages with different structure
        other_message = TaskMessageEntity(
            id=orm_id(),
            task_id=task.id,
            content=DataContentEntity(
                type="data",
                author="user",
                data={"different": "structure", "no_status": True},
            ),
            streaming_status="DONE",
        )
        await message_repo.create(other_message)

        # When - Filter by partial match on data.status="completed"
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"data": {"status": "completed"}}}',
            },
        )

        # Then - Should return only messages with status="completed"
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 3
        assert all(
            msg["content"]["data"]["status"] == "completed" for msg in filtered_messages
        )
        assert {m["id"] for m in filtered_messages} == {
            m.id for m in completed_messages
        }

        # When - Filter by partial match on data.status="pending"
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"data": {"status": "pending"}}}',
            },
        )

        # Then - Should return only messages with status="pending"
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 2
        assert all(
            msg["content"]["data"]["status"] == "pending" for msg in filtered_messages
        )

        # When - Filter by data type and partial data match
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"type": "data", "data": {"status": "completed"}}}',
            },
        )

        # Then - Should return completed data messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 3
        assert all(msg["content"]["type"] == "data" for msg in filtered_messages)
        assert all(
            msg["content"]["data"]["status"] == "completed" for msg in filtered_messages
        )

    async def test_list_messages_filter_data_content_deeply_nested(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering data messages with deeply nested data structures"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="nested-data-filter-agent",
            description="Agent for nested data content filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="nested-data-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for nested data content filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create data messages with deeply nested structures
        message_repo = isolated_repositories["task_message_repository"]

        # Messages with user.role="admin"
        admin_messages = []
        for i in range(2):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={
                        "metadata": {
                            "user": {"id": f"admin-{i}", "role": "admin", "level": 10},
                            "timestamp": "2024-01-01",
                        },
                        "result": {"success": True},
                    },
                ),
                streaming_status="DONE",
            )
            admin_messages.append(await message_repo.create(message))

        # Messages with user.role="viewer"
        viewer_messages = []
        for i in range(3):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={
                        "metadata": {
                            "user": {"id": f"viewer-{i}", "role": "viewer", "level": 1},
                            "timestamp": "2024-01-02",
                        },
                        "result": {"success": True},
                    },
                ),
                streaming_status="DONE",
            )
            viewer_messages.append(await message_repo.create(message))

        # Message with different nested structure
        other_message = TaskMessageEntity(
            id=orm_id(),
            task_id=task.id,
            content=DataContentEntity(
                type="data",
                author="agent",
                data={
                    "metadata": {"source": "external", "version": "1.0"},
                    "result": {"success": False},
                },
            ),
            streaming_status="DONE",
        )
        await message_repo.create(other_message)

        # When - Filter by deeply nested field: metadata.user.role="admin"
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"data": {"metadata": {"user": {"role": "admin"}}}}}',
            },
        )

        # Then - Should return only admin messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 2
        assert all(
            msg["content"]["data"]["metadata"]["user"]["role"] == "admin"
            for msg in filtered_messages
        )
        assert {m["id"] for m in filtered_messages} == {m.id for m in admin_messages}

        # When - Filter by deeply nested field: metadata.user.role="viewer"
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"data": {"metadata": {"user": {"role": "viewer"}}}}}',
            },
        )

        # Then - Should return only viewer messages
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 3
        assert all(
            msg["content"]["data"]["metadata"]["user"]["role"] == "viewer"
            for msg in filtered_messages
        )

        # When - Filter by result.success=True (matches both admin and viewer)
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"data": {"result": {"success": true}}}}',
            },
        )

        # Then - Should return admin and viewer messages (5 total)
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 5
        assert all(
            msg["content"]["data"]["result"]["success"] is True
            for msg in filtered_messages
        )

        # When - Filter by multiple nested criteria
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '{"content": {"data": {"metadata": {"user": {"role": "admin"}}, "result": {"success": true}}}}',
            },
        )

        # Then - Should return only admin messages with success=true
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 2
        assert all(
            msg["content"]["data"]["metadata"]["user"]["role"] == "admin"
            and msg["content"]["data"]["result"]["success"] is True
            for msg in filtered_messages
        )

    async def test_list_messages_paginated_with_filters(
        self, isolated_client, isolated_repositories
    ):
        """Test that cursor pagination works with filters"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="paginated-filter-agent",
            description="Agent for paginated filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="paginated-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for paginated filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create many text messages for pagination testing
        message_repo = isolated_repositories["task_message_repository"]
        text_messages = []
        for i in range(25):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=TextContentEntity(
                    type="text", author="user", content=f"Text message {i}"
                ),
                streaming_status="DONE",
            )
            text_messages.append(await message_repo.create(message))

        # Create some data messages (should be filtered out)
        for i in range(10):
            message = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data", author="agent", data={"value": i}
                ),
                streaming_status="DONE",
            )
            await message_repo.create(message)

        # When - Use paginated endpoint with text filter
        response = await isolated_client.get(
            "/messages/paginated",
            params={
                "task_id": task.id,
                "filters": '{"content": {"type": "text"}}',
                "limit": 10,
            },
        )

        # Then - Should return filtered results with pagination
        assert response.status_code == 200
        response_data = response.json()

        # Should have pagination metadata
        assert "data" in response_data
        assert "next_cursor" in response_data
        assert "has_more" in response_data

        # Should return only text messages
        assert len(response_data["data"]) == 10
        assert all(msg["content"]["type"] == "text" for msg in response_data["data"])

        # Should indicate more pages available
        assert response_data["has_more"] is True
        assert response_data["next_cursor"] is not None

        # When - Get next page with cursor
        response = await isolated_client.get(
            "/messages/paginated",
            params={
                "task_id": task.id,
                "filters": '{"content": {"type": "text"}}',
                "limit": 10,
                "cursor": response_data["next_cursor"],
            },
        )

        # Then - Should continue paginating through filtered results
        assert response.status_code == 200
        page2_data = response.json()
        assert len(page2_data["data"]) == 10
        assert all(msg["content"]["type"] == "text" for msg in page2_data["data"])

    async def test_list_messages_filter_validation_errors(
        self, isolated_client, test_task
    ):
        """Test that invalid filter JSON returns proper error"""
        # When - Send invalid JSON filter
        response = await isolated_client.get(
            "/messages",
            params={"task_id": test_task.id, "filters": '{"invalid": json}'},
        )

        # Then - Should return validation error
        assert response.status_code == 400

        # When - Send filter with invalid field
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": test_task.id,
                "filters": '{"nonexistent_field": "value"}',
            },
        )

        # This will return a 200 error and an empty list
        assert response.status_code == 200
        assert len(response.json()) == 0

    async def test_list_messages_filter_data_type_in_multiple_values(
        self, isolated_client, isolated_repositories
    ):
        """Test filtering data messages where content.data.type matches multiple values using $in"""
        # Given - Create agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="data-type-filter-agent",
            description="Agent for data type filter testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="data-type-filter-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for data type filter testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        message_repo = isolated_repositories["task_message_repository"]

        # Create messages with different data types
        report_status_messages = []
        for i in range(2):
            msg = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={"type": "report_status_update", "status": f"update_{i}"},
                ),
                streaming_status="DONE",
            )
            await message_repo.create(msg)
            report_status_messages.append(msg)

        reasoning_summary_messages = []
        for i in range(3):
            msg = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={"type": "reasoning_summary", "summary": f"reasoning_{i}"},
                ),
                streaming_status="DONE",
            )
            await message_repo.create(msg)
            reasoning_summary_messages.append(msg)

        # Create other data messages that should NOT be matched
        other_messages = []
        for data_type in ["progress_update", "error_report", "final_result"]:
            msg = TaskMessageEntity(
                id=orm_id(),
                task_id=task.id,
                content=DataContentEntity(
                    type="data",
                    author="agent",
                    data={"type": data_type, "info": "other data"},
                ),
                streaming_status="DONE",
            )
            await message_repo.create(msg)
            other_messages.append(msg)

        # When - Filter for messages where content.data.type is "report_status_update" OR "reasoning_summary"
        response = await isolated_client.get(
            "/messages",
            params={
                "task_id": task.id,
                "filters": '[{"content": {"data": {"type": "report_status_update"}}}, {"content": {"data": {"type": "reasoning_summary"}}}]',
            },
        )

        # Then - Should return only report_status_update and reasoning_summary messages (5 total)
        assert response.status_code == 200
        filtered_messages = response.json()
        assert len(filtered_messages) == 5

        # Verify all returned messages have the expected data types
        returned_types = {msg["content"]["data"]["type"] for msg in filtered_messages}
        assert returned_types == {"report_status_update", "reasoning_summary"}

        # Verify the correct message IDs are returned
        expected_ids = {
            m.id for m in report_status_messages + reasoning_summary_messages
        }
        actual_ids = {m["id"] for m in filtered_messages}
        assert actual_ids == expected_ids
