from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.agents_rpc import (
    CancelTaskRequest,
    SendEventRequest,
)
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.agents_rpc import SendMessageRequestEntity
from src.domain.entities.events import EventEntity
from src.domain.entities.task_message_updates import (
    StreamTaskMessageDeltaEntity,
    StreamTaskMessageDoneEntity,
    StreamTaskMessageFullEntity,
    StreamTaskMessageStartEntity,
)
from src.domain.entities.task_messages import (
    MessageAuthor,
    MessageStyle,
    TaskMessageContentType,
    TextContentEntity,
    TextFormat,
)
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_message_repository import TaskMessageRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.agent_acp_service import AgentACPService
from src.domain.services.task_message_service import TaskMessageService
from src.domain.services.task_service import AgentTaskService
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase

# UTC timezone constant
UTC = ZoneInfo("UTC")


class AsyncStreamMock:
    """Mock async iterator for testing stream_call functionality"""

    def __init__(self, responses):
        self.responses = responses
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.responses):
            raise StopAsyncIteration
        response = self.responses[self.index]
        self.index += 1
        return response


@pytest.fixture
def mock_http_gateway():
    """Mock HTTP gateway for testing external API calls"""
    mock = AsyncMock()
    return mock


@pytest.fixture
def agent_repository(postgres_session_maker):
    """Real AgentRepository using test PostgreSQL database"""
    return AgentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def agent_api_key_repository(postgres_session_maker):
    """Real AgentAPIKeyRepository using test PostgreSQL database"""
    return AgentAPIKeyRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def task_repository(postgres_session_maker):
    """Real TaskRepository using test PostgreSQL database"""
    return TaskRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def event_repository(postgres_session_maker):
    """Real EventRepository using test PostgreSQL database"""
    return EventRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def task_message_repository(mongodb_database):
    """Real TaskMessageRepository using test MongoDB database"""
    return TaskMessageRepository(mongodb_database)


@pytest.fixture
def agent_acp_service(mock_http_gateway, agent_repository, agent_api_key_repository):
    """Real AgentACPService instance with mocked HTTP gateway"""
    return AgentACPService(
        http_gateway=mock_http_gateway,
        agent_repository=agent_repository,
        agent_api_key_repository=agent_api_key_repository,
    )


@pytest.fixture
def task_service(
    task_repository,
    event_repository,
    agent_acp_service,
    redis_stream_repository,
):
    """Real AgentTaskService instance"""
    return AgentTaskService(
        task_repository=task_repository,
        event_repository=event_repository,
        acp_client=agent_acp_service,
        stream_repository=redis_stream_repository,
    )


@pytest.fixture
def task_message_service(task_message_repository):
    """Real TaskMessageService instance"""
    return TaskMessageService(
        message_repository=task_message_repository,
    )


@pytest.fixture
def authorization_service():
    """Mock AuthorizationService instance with no-op grant method"""
    service = AsyncMock()
    service.grant = AsyncMock(return_value=None)
    return service


@pytest.fixture
def agents_acp_use_case(
    agent_repository,
    agent_acp_service,
    task_service,
    task_message_service,
    authorization_service,
):
    """Real AgentsACPUseCase instance with required services and mocked authorization"""
    return AgentsACPUseCase(
        agent_repository=agent_repository,
        acp_client=agent_acp_service,
        task_service=task_service,
        task_message_service=task_message_service,
        authorization_service=authorization_service,
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for use case testing",
        acp_type=ACPType.ASYNC,
        status=AgentStatus.READY,
        acp_url="http://test-acp.example.com",
    )


@pytest.fixture
def sample_task():
    """Sample task entity for testing"""
    return TaskEntity(
        id=str(uuid4()),
        name="test-task",
        status=TaskStatus.RUNNING,
        status_reason="Test task for use case",
    )


@pytest.fixture
def sample_text_content():
    """Sample text content for testing"""
    return TextContentEntity(
        type=TaskMessageContentType.TEXT,
        content="Hello from use case test",
        author=MessageAuthor.USER,
        style=MessageStyle.STATIC,
        format=TextFormat.PLAIN,
    )


async def create_or_get_agent(agent_repository, agent):
    """Helper to create agent or get existing one"""
    try:
        return await agent_repository.create(agent)
    except Exception:
        # Agent might already exist, sync the ID
        try:
            existing = await agent_repository.get(name=agent.name)
            agent.id = existing.id
            return existing
        except ItemDoesNotExist:
            raise


@pytest.mark.asyncio
@pytest.mark.unit
class TestAgentsACPUseCase:
    """Test suite for AgentsACPUseCase"""

    async def test_agent_authentication(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        agent_api_key_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test agent authentication flow"""
        # Given - Create agent and internal API key first
        agent = await create_or_get_agent(agent_repository, sample_agent)
        agent_api_key = AgentAPIKeyEntity(
            id=str(uuid4()),
            name="test-api-key",
            agent_id=agent.id,
            api_key_type=AgentAPIKeyType.INTERNAL,
            api_key="test-internal-api-key",
        )
        await agent_api_key_repository.create(agent_api_key)

        # Mock successful HTTP response from ACP service
        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Ensure the request has the correct API key in headers
            assert kwargs["default_headers"]["x-agent-api-key"] == agent_api_key.api_key
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "Testing authentication",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity
        send_request = SendMessageRequestEntity(
            task_id=None,  # Will create new task
            content=sample_text_content,
            stream=False,
        )

        # Execute send message call to check the create_mock_stream assert above
        await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

    async def test_handle_message_send_sync_success(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test successful synchronous message sending"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful HTTP response from ACP service

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "Complete message in one chunk",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity
        send_request = SendMessageRequestEntity(
            task_id=None,  # Will create new task
            content=sample_text_content,
            stream=False,
        )

        # When
        result = await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].content.content == "Complete message in one chunk"
        assert result[0].content.author == MessageAuthor.AGENT

        # Verify HTTP call was made to stream_call because we are always using stream True with ACP
        mock_http_gateway.async_call.assert_not_called()

    #
    async def test_handle_message_send_sync_with_existing_task(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
        sample_text_content,
    ):
        """Test synchronous message sending with existing task"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="existing-task"
        )

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "Complete message in one chunk",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity with existing task
        send_request = SendMessageRequestEntity(
            task_id=created_task.id,
            content=sample_text_content,
            stream=False,
        )

        # When
        result = await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].content.content == "Complete message in one chunk"
        assert result[0].content.author == MessageAuthor.AGENT
        # Verify HTTP call was made to stream_call because we are always using stream True with ACP
        mock_http_gateway.async_call.assert_not_called()

    async def test_handle_message_send_stream_simple_text(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test streaming message sending with simple text deltas"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "start",
                        "message_id": "msg-123",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "",  # Initial empty content for START message
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": "Hello",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": " world!",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "done",
                        "index": 0,
                        "message_id": "msg-123",
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity for streaming
        send_request = SendMessageRequestEntity(
            task_id=None,  # Will create new task
            content=sample_text_content,
            stream=True,
        )

        # Store initial message count for database validation
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then
        assert len(updates) == 4  # START, DELTA, DELTA, DONE

        # Verify START message
        start_update = updates[0]
        assert isinstance(start_update, StreamTaskMessageStartEntity)
        assert start_update.index == 0
        assert hasattr(start_update, "parent_task_message")

        # Verify DELTA messages
        delta1 = updates[1]
        assert isinstance(delta1, StreamTaskMessageDeltaEntity)
        assert delta1.index == 0
        assert delta1.delta.text_delta == "Hello"

        delta2 = updates[2]
        assert isinstance(delta2, StreamTaskMessageDeltaEntity)
        assert delta2.index == 0
        assert delta2.delta.text_delta == " world!"

        # Verify DONE message
        done_update = updates[3]
        assert isinstance(done_update, StreamTaskMessageDoneEntity)
        assert done_update.index == 0

        # Verify database interactions - should have created messages
        final_message_count = len(await task_message_repository.list())
        assert (
            final_message_count > initial_message_count
        ), "New messages should have been created in database"

        # Get all messages from database to verify content
        all_messages = await task_message_repository.list()
        new_messages = all_messages[
            initial_message_count:
        ]  # Only the newly created messages

        # Should have at least 2 new messages (input + response)
        assert (
            len(new_messages) >= 2
        ), f"Expected at least 2 new messages (input + response), got {len(new_messages)}"

        # Verify we have both user input and agent response messages
        content_authors = {msg.content.author.value for msg in new_messages}
        assert "user" in content_authors, "Should have user input message in database"
        assert (
            "agent" in content_authors
        ), "Should have agent response message in database"

        # Find the agent response message and verify its final accumulated content
        agent_messages = [
            msg for msg in new_messages if msg.content.author == MessageAuthor.AGENT
        ]
        assert (
            len(agent_messages) >= 1
        ), "Should have at least one agent response message"

        # Verify the final accumulated content includes both deltas
        response_message = agent_messages[0]  # First agent response
        assert (
            "Hello" in response_message.content.content
        ), f"Expected 'Hello' in final content, got '{response_message.content.content}'"
        assert (
            "world!" in response_message.content.content
        ), f"Expected 'world!' in final content, got '{response_message.content.content}'"

    async def test_handle_message_send_stream_full_message(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test streaming with a FULL message (complete message in one chunk)"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "Complete message in one chunk",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity for streaming
        send_request = SendMessageRequestEntity(
            task_id=None,
            content=sample_text_content,
            stream=True,
        )

        # Store initial message count for database validation
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then
        assert len(updates) == 1  # Just the FULL message

        full_update = updates[0]
        assert isinstance(full_update, StreamTaskMessageFullEntity)
        assert full_update.index == 0
        assert full_update.content.content == "Complete message in one chunk"
        assert hasattr(full_update, "parent_task_message")

        # Verify database interactions - should have created messages
        final_message_count = len(await task_message_repository.list())
        assert (
            final_message_count > initial_message_count
        ), "New messages should have been created in database"

        # Get all messages from database to verify content
        all_messages = await task_message_repository.list()
        new_messages = all_messages[
            initial_message_count:
        ]  # Only the newly created messages

        # Should have at least 2 new messages (input + response)
        assert (
            len(new_messages) >= 2
        ), f"Expected at least 2 new messages (input + response), got {len(new_messages)}"

        # Verify we have both user input and agent response messages
        content_authors = {msg.content.author.value for msg in new_messages}
        assert "user" in content_authors, "Should have user input message in database"
        assert (
            "agent" in content_authors
        ), "Should have agent response message in database"

        # Find the agent response message and verify its content
        agent_messages = [
            msg for msg in new_messages if msg.content.author == MessageAuthor.AGENT
        ]
        assert (
            len(agent_messages) >= 1
        ), "Should have at least one agent response message"

        # Verify the FULL message content is correctly stored
        response_message = agent_messages[0]  # First agent response
        assert (
            response_message.content.content == "Complete message in one chunk"
        ), f"Expected complete message content, got '{response_message.content.content}'"

    async def test_handle_message_send_stream_multiple_indexes(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test streaming with multiple message indexes (concurrent messages)"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock streaming responses with two different message indexes
        mock_responses = [
            # Message index 0
            {
                "jsonrpc": "2.0",
                "result": {
                    "type": "delta",
                    "index": 0,
                    "delta": {
                        "type": "text",
                        "text_delta": "First",
                    },
                },
                "id": "message/send-",
            },
            # Message index 1
            {
                "jsonrpc": "2.0",
                "result": {
                    "type": "delta",
                    "index": 1,
                    "delta": {
                        "type": "text",
                        "text_delta": "Second",
                    },
                },
                "id": "message/send-",
            },
            # Continue message index 0
            {
                "jsonrpc": "2.0",
                "result": {
                    "type": "delta",
                    "index": 0,
                    "delta": {
                        "type": "text",
                        "text_delta": " message",
                    },
                },
                "id": "message/send-",
            },
            # Done with index 0
            {
                "jsonrpc": "2.0",
                "result": {
                    "type": "done",
                    "index": 0,
                    "message_id": "msg-0",
                },
                "id": "message/send-",
            },
            # Done with index 1
            {
                "jsonrpc": "2.0",
                "result": {
                    "type": "done",
                    "index": 1,
                    "message_id": "msg-1",
                },
                "id": "message/send-",
            },
        ]

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            # Update mock responses with correct request ID
            for response in mock_responses:
                response["id"] = request_id

            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity for streaming
        send_request = SendMessageRequestEntity(
            task_id=None,
            content=sample_text_content,
            stream=True,
        )

        # Store initial message count for database validation
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then - Should have START messages for both indexes plus all the deltas and dones
        # We expect: START(0), DELTA(0), START(1), DELTA(1), DELTA(0), DONE(0), DONE(1)
        assert len(updates) == 7

        # Verify we have messages for both indexes
        index_0_messages = [u for u in updates if u.index == 0]
        index_1_messages = [u for u in updates if u.index == 1]

        assert len(index_0_messages) == 4  # START, DELTA, DELTA, DONE
        assert len(index_1_messages) == 3  # START, DELTA, DONE

        # Verify database interactions - should have created messages
        final_message_count = len(await task_message_repository.list())
        assert (
            final_message_count > initial_message_count
        ), "New messages should have been created in database"

        # Get all messages from database to verify content
        all_messages = await task_message_repository.list()
        new_messages = all_messages[
            initial_message_count:
        ]  # Only the newly created messages

        # Should have at least 3 new messages (input + 2 response messages for different indexes)
        assert (
            len(new_messages) >= 3
        ), f"Expected at least 3 new messages (input + 2 responses), got {len(new_messages)}"

        # Verify we have both user input and agent response messages
        content_authors = {msg.content.author.value for msg in new_messages}
        assert "user" in content_authors, "Should have user input message in database"
        assert (
            "agent" in content_authors
        ), "Should have agent response messages in database"

        # Find the agent response messages - should have multiple for different indexes
        agent_messages = [
            msg for msg in new_messages if msg.content.author == MessageAuthor.AGENT
        ]
        assert (
            len(agent_messages) >= 2
        ), f"Should have at least 2 agent response messages for different indexes, got {len(agent_messages)}"

        # Verify the content includes expected text from both indexes
        agent_content = " ".join([msg.content.content for msg in agent_messages])
        assert (
            "First" in agent_content or "Second" in agent_content
        ), f"Expected content from multiple indexes, got '{agent_content}'"

    async def test_handle_task_create_error(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test error handling in task creation"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock HTTP error - create a function that raises when called
        def create_mock_stream_error(*args, **kwargs):
            raise Exception("ACP server connection failed")

        mock_http_gateway.async_call.side_effect = create_mock_stream_error

        # Create task creation request
        import uuid

        from src.api.schemas.agents_rpc import CreateTaskRequest

        unique_task_name = f"test-task-{uuid.uuid4().hex[:8]}"
        create_request = CreateTaskRequest(
            name=unique_task_name,
            params={"param1": "value1"},
        )
        with pytest.raises(Exception) as exc_info:
            await agents_acp_use_case._handle_task_create(
                agent=sample_agent,
                params=create_request,
            )

        assert "ACP server connection failed" in str(exc_info.value)

    async def test_handle_task_create_success(
        self, agents_acp_use_case, mock_http_gateway, agent_repository, sample_agent
    ):
        """Test successful task creation"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful task creation response
        from src.api.schemas.agents_rpc import CreateTaskRequest

        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            return {
                "jsonrpc": "2.0",
                "result": {"status": "created", "task_id": "new-task-id"},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Create task creation request
        import uuid

        unique_task_name = f"test-task-{uuid.uuid4().hex[:8]}"
        create_request = CreateTaskRequest(
            name=unique_task_name,
            params={"param1": "value1"},
        )

        # When
        result = await agents_acp_use_case._handle_task_create(
            agent=sample_agent,
            params=create_request,
        )

        # Then
        assert isinstance(result, TaskEntity)
        assert result.name == unique_task_name
        assert result.params == {
            "param1": "value1"
        }  # Verify params are stored in the created task
        assert result.status == TaskStatus.RUNNING

        # Verify HTTP call was made
        mock_http_gateway.async_call.assert_called_once()

    #
    async def test_handle_message_send_sync_error_handling(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test error handling in synchronous message sending"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock HTTP error - create a function that raises when called
        def create_mock_stream_error(*args, **kwargs):
            raise Exception("ACP server connection failed")

        mock_http_gateway.stream_call = create_mock_stream_error

        # Create SendMessageRequestEntity
        send_request = SendMessageRequestEntity(
            task_id=None,
            content=sample_text_content,
            stream=False,
        )

        # When / Then
        with pytest.raises(Exception) as exc_info:
            await agents_acp_use_case._handle_message_send_sync(
                agent=sample_agent,
                params=send_request,
            )

        assert "ACP server connection failed" in str(exc_info.value)

    async def test_delta_accumulator_flush_scenario(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test flush_aggregated_deltas when stream ends without DONE message"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": "Incomplete",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": " message",
                        },
                    },
                    "id": request_id,
                },
                # Stream ends here without DONE - should trigger flush
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity for streaming
        send_request = SendMessageRequestEntity(
            task_id=None,
            content=sample_text_content,
            stream=True,
        )

        # Store initial message count for database validation
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then - Should have START and DELTA messages, and flush should happen after stream ends
        assert len(updates) == 3  # START, DELTA, DELTA

        # Verify the delta accumulation worked
        start_update = updates[0]
        assert isinstance(start_update, StreamTaskMessageStartEntity)

        delta1 = updates[1]
        assert isinstance(delta1, StreamTaskMessageDeltaEntity)
        assert delta1.delta.text_delta == "Incomplete"

        delta2 = updates[2]
        assert isinstance(delta2, StreamTaskMessageDeltaEntity)
        assert delta2.delta.text_delta == " message"

        # The flush_aggregated_deltas should have been called after the stream ended
        # and updated the database with the accumulated content "Incomplete message"

        # Verify database interactions - should have created messages
        final_message_count = len(await task_message_repository.list())
        assert (
            final_message_count > initial_message_count
        ), "New messages should have been created in database"

        # Get all messages from database to verify content
        all_messages = await task_message_repository.list()
        new_messages = all_messages[
            initial_message_count:
        ]  # Only the newly created messages

        # Should have at least 2 new messages (input + response)
        assert (
            len(new_messages) >= 2
        ), f"Expected at least 2 new messages (input + response), got {len(new_messages)}"

        # Verify we have both user input and agent response messages
        content_authors = {msg.content.author.value for msg in new_messages}
        assert "user" in content_authors, "Should have user input message in database"
        assert (
            "agent" in content_authors
        ), "Should have agent response message in database"

        # Find the agent response message and verify accumulated content was flushed
        agent_messages = [
            msg for msg in new_messages if msg.content.author == MessageAuthor.AGENT
        ]
        assert (
            len(agent_messages) >= 1
        ), "Should have at least one agent response message"

        # Verify the deltas were properly accumulated and flushed to database
        response_message = agent_messages[0]  # First agent response
        assert (
            "Incomplete" in response_message.content.content
        ), f"Expected 'Incomplete' in flushed content, got '{response_message.content.content}'"
        assert (
            "message" in response_message.content.content
        ), f"Expected 'message' in flushed content, got '{response_message.content.content}'"

    async def test_handle_message_send_stream_complex_mixed_content_types(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test streaming with 3 indexes: ToolRequest, ToolResponse, and Text content types with database validation"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                # === INDEX 0: Tool Request Content ===
                # START for tool request
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "start",
                        "index": 0,
                        "content": {
                            "type": "tool_request",
                            "author": "agent",
                            "style": "static",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "arguments": {},
                        },
                    },
                    "id": request_id,
                },
                # DELTA for tool request arguments
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "tool_request",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "arguments_delta": '{"location": "San',
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "tool_request",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "arguments_delta": ' Francisco"}',
                        },
                    },
                    "id": request_id,
                },
                # FULL message for tool request
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "tool_request",
                            "author": "agent",
                            "style": "static",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "arguments": {"location": "San Francisco"},
                        },
                    },
                    "id": request_id,
                },
                # === INDEX 1: Tool Response Content ===
                # START for tool response
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "start",
                        "index": 1,
                        "content": {
                            "type": "tool_response",
                            "author": "agent",
                            "style": "static",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "content": "",
                        },
                    },
                    "id": request_id,
                },
                # DELTA for tool response content
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 1,
                        "delta": {
                            "type": "tool_response",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "content_delta": "Temperature: 72°F,",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 1,
                        "delta": {
                            "type": "tool_response",
                            "tool_call_id": "call_001",
                            "name": "get_weather",
                            "content_delta": " Sunny",
                        },
                    },
                    "id": request_id,
                },
                # === INDEX 2: Text Content (Agent) ===
                # START for text content
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "start",
                        "index": 2,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
                # DELTA for text content
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 2,
                        "delta": {
                            "type": "text",
                            "text_delta": "Based on the weather data,",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 2,
                        "delta": {
                            "type": "text",
                            "text_delta": " it's a beautiful day in SF!",
                        },
                    },
                    "id": request_id,
                },
                # === DONE messages for all indexes ===
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "done",
                        "index": 0,
                        "message_id": "msg-tool-request",
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "done",
                        "index": 1,
                        "message_id": "msg-tool-response",
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "done",
                        "index": 2,
                        "message_id": "msg-text-agent",
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity for streaming
        send_request = SendMessageRequestEntity(
            task_id=None,  # Will create new task
            content=sample_text_content,
            stream=True,
        )

        # Store initial message count for comparison
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then - Verify all streaming updates were generated
        assert (
            len(updates) == 12
        )  # 3 START + 6 DELTA + 1 FULL + 2 DONE = 12 updates (index 0 completed with FULL so no separate DONE)

        # Verify database interactions - should have created messages
        final_message_count = len(await task_message_repository.list())
        assert (
            final_message_count > initial_message_count
        ), "New messages should have been created in database"

        # Get all messages from database to verify content
        all_messages = await task_message_repository.list()
        new_messages = all_messages[
            initial_message_count:
        ]  # Only the newly created messages

        # Should have at least 3 new messages (one for each index) plus deltas potentially stored
        assert (
            len(new_messages) >= 3
        ), f"Expected at least 3 new messages, got {len(new_messages)}"

        # Verify we have messages with different content types
        content_types_found = {msg.content.type.value for msg in new_messages}
        expected_types = {"tool_request", "tool_response", "text"}

        # At least some of the expected types should be present (depends on how deltas vs full messages are stored)
        assert (
            len(content_types_found.intersection(expected_types)) > 0
        ), f"Expected some of {expected_types}, got {content_types_found}"

        # Verify index distribution - should have messages for different indexes
        indexes_found = {getattr(update, "index", None) for update in updates}
        assert indexes_found == {
            0,
            1,
            2,
        }, f"Expected indexes {{0, 1, 2}}, got {indexes_found}"

        # Verify specific update types were generated
        start_updates = [
            u for u in updates if isinstance(u, StreamTaskMessageStartEntity)
        ]
        delta_updates = [
            u for u in updates if isinstance(u, StreamTaskMessageDeltaEntity)
        ]
        full_updates = [
            u for u in updates if isinstance(u, StreamTaskMessageFullEntity)
        ]
        done_updates = [
            u for u in updates if isinstance(u, StreamTaskMessageDoneEntity)
        ]

        assert (
            len(start_updates) == 3
        ), f"Expected 3 START updates, got {len(start_updates)}"
        assert (
            len(delta_updates) == 6
        ), f"Expected 6 DELTA updates, got {len(delta_updates)}"
        assert (
            len(full_updates) == 1
        ), f"Expected 1 FULL update, got {len(full_updates)}"
        assert (
            len(done_updates) == 2
        ), f"Expected 2 DONE updates, got {len(done_updates)} (index 0 completed with FULL message)"

        # Verify content types in START messages
        start_content_types = {update.content.type.value for update in start_updates}
        assert start_content_types == {
            "tool_request",
            "tool_response",
            "text",
        }, f"Expected all content types in START, got {start_content_types}"

    async def test_handle_task_cancel_success(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
    ):
        """Test successful task cancellation"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="cancel-test-task"
        )

        # Mock successful cancellation response
        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            return {
                "jsonrpc": "2.0",
                "result": {"status": "cancelled", "task_id": created_task.id},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Create task cancellation request
        cancel_request = CancelTaskRequest(
            task_id=created_task.id,
        )

        # When
        result = await agents_acp_use_case._handle_task_cancel(
            agent=sample_agent,
            params=cancel_request,
        )

        # Then
        assert isinstance(result, TaskEntity)
        assert result.id == created_task.id

        # Verify HTTP call was made
        mock_http_gateway.async_call.assert_called_once()

    async def test_handle_task_cancel_with_task_name(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
    ):
        """Test task cancellation using task_name instead of task_id"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="named-cancel-task"
        )

        # Mock successful cancellation response
        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            return {
                "jsonrpc": "2.0",
                "result": {"status": "cancelled", "task_id": created_task.id},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Create task cancellation request with task_name
        cancel_request = CancelTaskRequest(
            task_name="named-cancel-task",
        )

        # When
        result = await agents_acp_use_case._handle_task_cancel(
            agent=sample_agent,
            params=cancel_request,
        )

        # Then
        assert isinstance(result, TaskEntity)
        assert result.id == created_task.id

    async def test_handle_event_send_success(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        event_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test successful event sending"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="event-test-task"
        )

        # Mock successful event response
        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            return {
                "jsonrpc": "2.0",
                "result": {"status": "event_sent", "event_id": "event-123"},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Create event send request
        event_request = SendEventRequest(
            task_id=created_task.id,
            content=sample_text_content,
        )

        # Store initial event count for database validation
        initial_event_count = len(await event_repository.list())

        # When
        result = await agents_acp_use_case._handle_event_send(
            agent=sample_agent,
            params=event_request,
        )

        # Then
        assert isinstance(result, EventEntity)

        # Verify HTTP call was made
        mock_http_gateway.async_call.assert_called_once()

        # Verify database interactions - should have created an event
        final_event_count = len(await event_repository.list())
        assert (
            final_event_count > initial_event_count
        ), "New event should have been created in database"

        # Get all events from database to verify content
        all_events = await event_repository.list()
        new_events = all_events[initial_event_count:]  # Only the newly created events

        # Should have exactly 1 new event
        assert (
            len(new_events) == 1
        ), f"Expected exactly 1 new event, got {len(new_events)}"

        # Verify the event was properly stored
        created_event = new_events[0]
        assert (
            created_event.task_id == created_task.id
        ), f"Expected task_id {created_task.id}, got {created_event.task_id}"
        assert (
            created_event.content == sample_text_content
        ), "Expected event content to match input"

    async def test_handle_event_send_with_task_name(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        event_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test event sending using task_name instead of task_id"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="named-event-task"
        )

        # Mock successful event response
        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            return {
                "jsonrpc": "2.0",
                "result": {"status": "event_sent", "event_id": "event-456"},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Create event send request with task_name
        event_request = SendEventRequest(
            task_name="named-event-task",
            content=sample_text_content,
        )

        # Store initial event count for database validation
        initial_event_count = len(await event_repository.list())

        # When
        result = await agents_acp_use_case._handle_event_send(
            agent=sample_agent,
            params=event_request,
        )

        # Then
        assert isinstance(result, EventEntity)

        # Verify database interactions - should have created an event
        final_event_count = len(await event_repository.list())
        assert (
            final_event_count > initial_event_count
        ), "New event should have been created in database"

        # Get all events from database to verify content
        all_events = await event_repository.list()
        new_events = all_events[initial_event_count:]  # Only the newly created events

        # Should have exactly 1 new event
        assert (
            len(new_events) == 1
        ), f"Expected exactly 1 new event, got {len(new_events)}"

        # Verify the event was properly stored
        created_event = new_events[0]
        assert (
            created_event.task_id == created_task.id
        ), f"Expected task_id {created_task.id}, got {created_event.task_id}"
        assert (
            created_event.content == sample_text_content
        ), "Expected event content to match input"

    async def test_handle_event_send_with_request_headers(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        event_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test event sending with request headers forwarding"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="event-headers-task"
        )

        # Mock successful event response and verify headers are forwarded via HTTP
        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            # HTTP headers are passed as default_headers parameter
            headers = kwargs.get("default_headers", {})

            # Headers should NOT be in params body (sent via HTTP instead)
            assert "params" in payload
            assert payload["params"]["request"] is None

            # Verify filtered headers are in HTTP headers (only x-* headers)
            assert "x-trace-id" in headers
            assert headers["x-trace-id"] == "trace-789"
            assert "x-user-id" in headers
            assert headers["x-user-id"] == "user-123"
            # Blocked headers should NOT be present
            assert (
                "content-type" not in headers
                or not headers.get("content-type") == "application/json"
            )

            return {
                "jsonrpc": "2.0",
                "result": {"status": "event_sent", "event_id": "event-789"},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Request headers to forward - mix of allowed and blocked headers
        request_headers = {
            "x-trace-id": "trace-789",  # Allowed: x-* prefix
            "x-user-id": "user-123",  # Allowed: x-* prefix
            "content-type": "application/json",  # Blocked: no x-* prefix
        }

        # Create event send request
        event_request = SendEventRequest(
            task_id=created_task.id,
            content=sample_text_content,
        )

        # Store initial event count for database validation
        initial_event_count = len(await event_repository.list())

        # When
        result = await agents_acp_use_case._handle_event_send(
            agent=sample_agent,
            params=event_request,
            request_headers=request_headers,
        )

        # Then
        assert isinstance(result, EventEntity)

        # Verify database interactions - should have created an event
        final_event_count = len(await event_repository.list())
        assert (
            final_event_count > initial_event_count
        ), "New event should have been created in database"

        # Verify HTTP call was made (mock_async_call will assert headers)
        mock_http_gateway.async_call.assert_called_once()

    async def test_handle_event_send_without_request_headers(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        event_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test event sending without request headers (backwards compatibility)"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="event-no-headers-task"
        )

        # Mock successful event response and verify request field is None
        async def mock_async_call(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "")
            # Verify request field is None or not present
            if "request" in payload.get("params", {}):
                assert payload["params"]["request"] is None
            return {
                "jsonrpc": "2.0",
                "result": {"status": "event_sent", "event_id": "event-999"},
                "id": request_id,
            }

        mock_http_gateway.async_call.side_effect = mock_async_call

        # Create event send request
        event_request = SendEventRequest(
            task_id=created_task.id,
            content=sample_text_content,
        )

        # Store initial event count for database validation
        initial_event_count = len(await event_repository.list())

        # When - Call without request_headers parameter
        result = await agents_acp_use_case._handle_event_send(
            agent=sample_agent,
            params=event_request,
        )

        # Then
        assert isinstance(result, EventEntity)

        # Verify database interactions - should have created an event
        final_event_count = len(await event_repository.list())
        assert (
            final_event_count > initial_event_count
        ), "New event should have been created in database"

        # Verify HTTP call was made (mock_async_call will assert no headers)
        mock_http_gateway.async_call.assert_called_once()

    async def test_handle_event_send_error_no_task_specified(
        self, agents_acp_use_case, sample_agent, sample_text_content
    ):
        """Test error handling when neither task_id nor task_name are provided"""
        # Given - Create event send request without task identification
        event_request = SendEventRequest(
            content=sample_text_content,
        )

        # When / Then
        from src.domain.exceptions import ClientError

        with pytest.raises(ClientError) as exc_info:
            await agents_acp_use_case._handle_event_send(
                agent=sample_agent,
                params=event_request,
            )

        assert "Either task_id or task_name must be provided" in str(exc_info.value)

    async def test_handle_message_send_sync_with_task_name(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
        sample_text_content,
    ):
        """Test synchronous message sending using task_name instead of task_id"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="named-message-task"
        )
        assert created_task.name == "named-message-task"

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "Response to named task",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity with task_name
        send_request = SendMessageRequestEntity(
            task_name="named-message-task",
            content=sample_text_content,
            stream=False,
        )

        # When
        result = await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

        # Then
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].content.content == "Response to named task"
        assert result[0].content.author == MessageAuthor.AGENT

    async def test_handle_message_send_stream_with_task_name(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test streaming message sending using task_name instead of task_id"""
        # Given - Create agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="named-stream-task"
        )

        assert created_task.name == "named-stream-task"

        # Setup async generator mock for stream_call - extract request ID dynamically
        def create_mock_stream(*args, **kwargs):
            # Extract request ID from the payload
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": "Stream response ",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": "to named task",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "done",
                        "index": 0,
                        "message_id": "msg-123",
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity with task_name for streaming
        send_request = SendMessageRequestEntity(
            task_name="named-stream-task",
            content=sample_text_content,
            stream=True,
        )

        # Store initial message count for database validation
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then
        assert len(updates) == 4  # START, DELTA, DELTA, DONE

        # Verify START message
        start_update = updates[0]
        assert isinstance(start_update, StreamTaskMessageStartEntity)
        assert start_update.index == 0

        # Verify database interactions - should have created messages
        final_message_count = len(await task_message_repository.list())
        assert (
            final_message_count > initial_message_count
        ), "New messages should have been created in database"

        # Get all messages from database to verify content
        all_messages = await task_message_repository.list()
        new_messages = all_messages[initial_message_count:]

        # Verify we have both user input and agent response messages
        content_authors = {msg.content.author.value for msg in new_messages}
        assert "user" in content_authors, "Should have user input message in database"
        assert (
            "agent" in content_authors
        ), "Should have agent response message in database"

        # Find the agent response message and verify its final accumulated content
        agent_messages = [
            msg for msg in new_messages if msg.content.author == MessageAuthor.AGENT
        ]
        assert (
            len(agent_messages) >= 1
        ), "Should have at least one agent response message"

        # Verify the final accumulated content includes both deltas
        response_message = agent_messages[0]
        assert (
            "Stream response" in response_message.content.content
        ), f"Expected 'Stream response' in final content, got '{response_message.content.content}'"
        assert (
            "to named task" in response_message.content.content
        ), f"Expected 'to named task' in final content, got '{response_message.content.content}'"

    async def test_handle_message_send_sync_with_task_params(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
        sample_text_content,
    ):
        """Test synchronous message sending with task_params (creates new task with params)"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Setup async generator mock for stream_call
        def create_mock_stream(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "full",
                        "index": 0,
                        "content": {
                            "type": "text",
                            "author": "agent",
                            "style": "static",
                            "format": "plain",
                            "content": "Response to task with params",
                            "attachments": None,
                        },
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity with task_params
        import uuid

        unique_task_name = f"task-with-params-{uuid.uuid4().hex[:8]}"
        task_params = {"param1": "value1", "param2": 42, "nested": {"key": "value"}}

        send_request = SendMessageRequestEntity(
            task_name=unique_task_name,
            content=sample_text_content,
            stream=False,
            task_params=task_params,
        )

        # When
        result = await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

        # Then
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].content.content == "Response to task with params"

        # Verify the task was created with the correct params
        created_task = await task_service.get_task(name=unique_task_name)
        assert created_task is not None
        assert created_task.name == unique_task_name
        assert created_task.params == task_params

    async def test_handle_message_send_stream_with_task_params(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        task_message_repository,
        sample_agent,
        sample_text_content,
    ):
        """Test streaming message sending with task_params (creates new task with params)"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Setup async generator mock for stream_call
        def create_mock_stream(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")

            mock_responses = [
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": "Streaming with ",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "delta",
                        "index": 0,
                        "delta": {
                            "type": "text",
                            "text_delta": "task params",
                        },
                    },
                    "id": request_id,
                },
                {
                    "jsonrpc": "2.0",
                    "result": {
                        "type": "done",
                        "index": 0,
                        "message_id": "msg-123",
                    },
                    "id": request_id,
                },
            ]
            return AsyncStreamMock(mock_responses)

        mock_http_gateway.stream_call = create_mock_stream

        # Create SendMessageRequestEntity with task_params
        import uuid

        unique_task_name = f"stream-task-params-{uuid.uuid4().hex[:8]}"
        task_params = {
            "timeout": 300,
            "max_retries": 3,
            "config": {"debug": True},
        }

        send_request = SendMessageRequestEntity(
            task_name=unique_task_name,
            content=sample_text_content,
            stream=True,
            task_params=task_params,
        )

        # Store initial message count
        initial_message_count = len(await task_message_repository.list())

        # When
        updates = []
        async for update in agents_acp_use_case._handle_message_send_stream(
            agent=sample_agent,
            params=send_request,
        ):
            updates.append(update)

        # Then
        assert len(updates) == 4  # START, DELTA, DELTA, DONE

        # Verify database interactions
        final_message_count = len(await task_message_repository.list())
        assert final_message_count > initial_message_count

        # Verify the task was created with the correct params
        created_task = await task_service.get_task(name=unique_task_name)
        assert created_task is not None
        assert created_task.name == unique_task_name
        assert created_task.params == task_params

        # Verify the messages were created correctly
        all_messages = await task_message_repository.list()
        new_messages = all_messages[initial_message_count:]
        agent_messages = [
            msg for msg in new_messages if msg.content.author == MessageAuthor.AGENT
        ]
        assert len(agent_messages) >= 1

        response_message = agent_messages[0]
        assert "Streaming with" in response_message.content.content
        assert "task params" in response_message.content.content
        response_message = agent_messages[0]
        assert "Streaming with" in response_message.content.content
        assert "task params" in response_message.content.content

    async def test_both_task_id_and_task_name_raises_validation_error(
        self,
        sample_text_content,
    ):
        """Test that providing both task_id and task_name raises validation error"""
        # When / Then - Should raise ValueError at entity level
        with pytest.raises(ValueError) as exc_info:
            SendMessageRequestEntity(
                task_id="some-id",
                task_name="some-name",
                content=sample_text_content,
                stream=False,
            )

        assert "Cannot provide both task_id and task_name" in str(exc_info.value)

    async def test_update_task_params_for_existing_task(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
        sample_text_content,
    ):
        """Test that task_params are updated when sending message to existing task"""
        # Given - Create agent and task with initial params
        await create_or_get_agent(agent_repository, sample_agent)
        initial_params = {"timeout": 300, "retries": 1}
        created_task = await task_service.create_task(
            agent=sample_agent,
            task_name="update-params-task",
            task_params=initial_params,
        )

        # Verify initial params
        assert created_task.params == initial_params

        # Setup mock response
        def create_mock_stream(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")
            return AsyncStreamMock(
                [
                    {
                        "jsonrpc": "2.0",
                        "result": {
                            "type": "full",
                            "index": 0,
                            "content": {
                                "type": "text",
                                "author": "agent",
                                "style": "static",
                                "format": "plain",
                                "content": "Response",
                                "attachments": None,
                            },
                        },
                        "id": request_id,
                    }
                ]
            )

        mock_http_gateway.stream_call = create_mock_stream

        # Send message with updated params
        updated_params = {"timeout": 600, "retries": 3, "debug": True}
        send_request = SendMessageRequestEntity(
            task_name="update-params-task",
            task_params=updated_params,
            content=sample_text_content,
            stream=False,
        )

        # When
        result = await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

        # Then - params should be updated
        assert isinstance(result, list)
        updated_task = await task_service.get_task(name="update-params-task")
        assert updated_task.params == updated_params
        assert updated_task.params != initial_params

    async def test_task_params_unchanged_when_same(
        self,
        agents_acp_use_case,
        mock_http_gateway,
        agent_repository,
        task_service,
        sample_agent,
        sample_text_content,
    ):
        """Test that task is not updated if params are the same"""
        # Given - Create agent and task with params
        await create_or_get_agent(agent_repository, sample_agent)
        task_params = {"timeout": 300}
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="same-params-task", task_params=task_params
        )

        assert created_task.name == "same-params-task"
        assert created_task.params == task_params

        # Setup mock response
        def create_mock_stream(*args, **kwargs):
            payload = kwargs.get("payload", {})
            request_id = payload.get("id", "message/send-")
            return AsyncStreamMock(
                [
                    {
                        "jsonrpc": "2.0",
                        "result": {
                            "type": "full",
                            "index": 0,
                            "content": {
                                "type": "text",
                                "author": "agent",
                                "style": "static",
                                "format": "plain",
                                "content": "Response",
                                "attachments": None,
                            },
                        },
                        "id": request_id,
                    }
                ]
            )

        mock_http_gateway.stream_call = create_mock_stream

        # Send message with same params
        send_request = SendMessageRequestEntity(
            task_name="same-params-task",
            task_params=task_params,  # Same params
            content=sample_text_content,
            stream=False,
        )

        # When
        result = await agents_acp_use_case._handle_message_send_sync(
            agent=sample_agent,
            params=send_request,
        )

        # Then - task should not be updated
        assert isinstance(result, list)
        task_after = await task_service.get_task(name="same-params-task")
        # Params should still be the same
        assert task_after.params == task_params
