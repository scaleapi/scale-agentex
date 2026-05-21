from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.task_messages import TextContent
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.events import EventEntity
from src.domain.entities.task_messages import (
    DataContentEntity,
    MessageAuthor,
    MessageStyle,
    TextContentEntity,
    TextFormat,
    ToolRequestContentEntity,
    ToolResponseContentEntity,
)
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.services.agent_acp_service import (
    AgentACPService,
    filter_request_headers,
)

# UTC timezone constant
UTC = ZoneInfo("UTC")


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
def mock_request():
    request = MagicMock()
    request.state = MagicMock()
    request.state.principal_context = None
    request.state.agent_identity = None
    request.headers = {}
    return request


@pytest.fixture
def agent_acp_service(
    mock_http_gateway, agent_repository, agent_api_key_repository, mock_request
):
    """Create AgentACPService instance with mocked HTTP gateway and real repository"""
    return AgentACPService(
        http_gateway=mock_http_gateway,
        agent_repository=agent_repository,
        agent_api_key_repository=agent_api_key_repository,
        request=mock_request,
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for ACP service testing",
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
        status_reason="Test task for ACP service",
    )


@pytest.fixture
def sample_event(sample_task, sample_agent):
    """Sample event entity for testing"""
    return EventEntity(
        id=str(uuid4()),
        task_id=sample_task.id,
        agent_id=sample_agent.id,
        sequence_id=1,
        content=TextContent(
            content="Test event content",
            author=MessageAuthor.AGENT,
        ),
    )


@pytest.fixture
def sample_text_content():
    """Sample text content for testing"""
    return TextContent(
        content="Hello from ACP service test",
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
class TestAgentACPService:
    """Test suite for AgentACPService"""

    async def test_create_task_success(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
    ):
        """Test successful task creation via JSON-RPC"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful HTTP response with correct ID format
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.TASK_CREATE}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {"status": "created", "task_id": sample_task.id},
            "id": expected_request_id,  # Use the same format as the service
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.create_task(
            agent=sample_agent,
            task=sample_task,
            acp_url="http://test-acp.example.com",
            params={"test_param": "value"},
        )

        # Then
        assert result["status"] == "created"
        assert result["task_id"] == sample_task.id

        # Verify HTTP call was made correctly
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["url"] == "http://test-acp.example.com/api"
        assert call_args[1]["timeout"] == 60

        # Verify JSON-RPC request format
        payload = call_args[1]["payload"]
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "task/create"
        assert payload["id"] == expected_request_id
        assert "params" in payload

    async def test_send_message_success(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_text_content,
    ):
        """Test successful message sending via JSON-RPC"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful response with text content
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.MESSAGE_SEND}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {
                "type": "text",
                "author": "agent",
                "style": "static",
                "format": "plain",
                "content": "Response from ACP server",
                "attachments": None,
            },
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.send_message(
            agent=sample_agent,
            task=sample_task,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert isinstance(result, TextContentEntity)
        assert result.content == "Response from ACP server"
        assert result.author == MessageAuthor.AGENT

        # Verify HTTP call
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert payload["method"] == "message/send"
        assert payload["params"]["stream"] is False

    async def test_send_message_includes_delegation_headers(
        self,
        agent_acp_service,
        mock_http_gateway,
        mock_request,
        agent_repository,
        sample_agent,
        sample_task,
        sample_text_content,
    ):
        """User principals get delegation headers on outbound ACP calls."""
        await create_or_get_agent(agent_repository, sample_agent)

        mock_request.state.principal_context = type(
            "Principal",
            (),
            {"user_id": "user-1", "account_id": "acct-1"},
        )()
        mock_request.state.agent_identity = None
        mock_request.headers = {
            "x-api-key": "user-delegation-key",
            "x-selected-account-id": "acct-1",
        }

        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.MESSAGE_SEND}-{sample_task.id}"
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "type": "text",
                "author": "agent",
                "style": "static",
                "format": "plain",
                "content": "ok",
                "attachments": None,
            },
            "id": expected_request_id,
        }

        await agent_acp_service.send_message(
            agent=sample_agent,
            task=sample_task,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        )

        http_headers = mock_http_gateway.async_call.call_args[1]["default_headers"]
        assert http_headers["x-acting-user-api-key"] == "user-delegation-key"
        assert http_headers["x-acting-as-agent"] == sample_agent.id
        assert http_headers["x-selected-account-id"] == "acct-1"
        assert "x-api-key" not in http_headers

    async def test_send_event_delegation_not_raw_api_key_passthrough(
        self,
        agent_acp_service,
        mock_http_gateway,
        mock_request,
        agent_repository,
        sample_agent,
        sample_task,
        sample_event,
    ):
        """EVENT_SEND must not passthrough x-api-key; only x-acting-user-api-key."""
        await create_or_get_agent(agent_repository, sample_agent)

        mock_request.state.principal_context = type(
            "Principal",
            (),
            {"user_id": "user-1", "account_id": "acct-1"},
        )()
        mock_request.state.agent_identity = None
        mock_request.headers = {"x-api-key": "user-delegation-key"}

        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.EVENT_SEND}-{sample_task.id}"
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "event_sent", "event_id": sample_event.id},
            "id": expected_request_id,
        }

        await agent_acp_service.send_event(
            agent=sample_agent,
            event=sample_event,
            task=sample_task,
            acp_url="http://test-acp.example.com",
            request_headers={
                "x-api-key": "user-delegation-key",
                "x-trace-id": "trace-456",
            },
        )

        http_headers = mock_http_gateway.async_call.call_args[1]["default_headers"]
        assert http_headers["x-acting-user-api-key"] == "user-delegation-key"
        assert http_headers["x-trace-id"] == "trace-456"
        assert "x-api-key" not in http_headers

    async def test_get_headers_server_request_id_wins_over_passthrough(
        self,
        agent_acp_service,
        mock_request,
        sample_agent,
    ):
        """Server-generated x-request-id must override client passthrough."""
        mock_request.state.principal_context = None
        mock_request.state.agent_identity = None
        mock_request.headers = {}

        with patch.object(
            agent_acp_service,
            "get_agent_auth_headers",
            new=AsyncMock(return_value={}),
        ):
            headers = await agent_acp_service.get_headers(
                sample_agent,
                request_headers={"x-request-id": "client-request-id"},
            )

        assert headers["x-request-id"] != "client-request-id"
        assert len(headers["x-request-id"]) > 0

    async def test_send_message_success_data(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_text_content,
    ):
        """Test successful message sending via JSON-RPC"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful response with text content
        from src.domain.entities.agents_rpc import AgentRPCMethod

        response_content = {
            "message": "Response from ACP server",
            "key": "value",
            "key2": 1.0,
        }
        expected_request_id = f"{AgentRPCMethod.MESSAGE_SEND}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {
                "type": "data",
                "author": "agent",
                "style": "static",
                "format": "plain",
                "data": response_content,
                "attachments": None,
            },
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.send_message(
            agent=sample_agent,
            task=sample_task,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert isinstance(result, DataContentEntity)
        assert result.data == response_content
        assert result.author == MessageAuthor.AGENT

        # Verify HTTP call
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert payload["method"] == "message/send"
        assert payload["params"]["stream"] is False

    async def test_send_message_success_tool_request(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_text_content,
    ):
        """Test successful message sending via JSON-RPC"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful response with text content
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.MESSAGE_SEND}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {
                "type": "tool_request",
                "author": "agent",
                "style": "static",
                "format": "plain",
                "tool_call_id": "123",
                "name": "get_weather",
                "arguments": {
                    "location": "San Francisco, CA",
                    "units": "celsius",
                },
                "attachments": None,
            },
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.send_message(
            agent=sample_agent,
            task=sample_task,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert isinstance(result, ToolRequestContentEntity)
        assert result.tool_call_id == "123"
        assert result.name == "get_weather"
        assert result.arguments == {
            "location": "San Francisco, CA",
            "units": "celsius",
        }
        assert result.author == MessageAuthor.AGENT

        # Verify HTTP call
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert payload["method"] == "message/send"
        assert payload["params"]["stream"] is False

    async def test_send_message_success_tool_response(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_text_content,
    ):
        """Test successful message sending via JSON-RPC"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful response with text content
        from src.domain.entities.agents_rpc import AgentRPCMethod

        response_content = {
            "temperature": 22.5,
            "description": "Sunny with a chance of clouds",
        }
        expected_request_id = f"{AgentRPCMethod.MESSAGE_SEND}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {
                "type": "tool_response",
                "author": "agent",
                "style": "static",
                "format": "plain",
                "tool_call_id": "123",
                "name": "get_weather",
                "content": response_content,
                "attachments": None,
            },
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.send_message(
            agent=sample_agent,
            task=sample_task,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert isinstance(result, ToolResponseContentEntity)
        assert result.tool_call_id == "123"
        assert result.name == "get_weather"
        assert result.content == response_content
        assert result.author == MessageAuthor.AGENT

        # Verify HTTP call
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert payload["method"] == "message/send"
        assert payload["params"]["stream"] is False

    async def test_cancel_task_success(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
    ):
        """Test successful task cancellation"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful cancellation response
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.TASK_CANCEL}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {"status": "cancelled", "task_id": sample_task.id},
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.cancel_task(
            agent=sample_agent,
            task=sample_task,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert result["status"] == "cancelled"
        assert result["task_id"] == sample_task.id

        # Verify call
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert payload["method"] == "task/cancel"

    async def test_send_event_success(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_event,
    ):
        """Test successful event sending"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful response
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.EVENT_SEND}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {"status": "event_sent", "event_id": sample_event.id},
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When
        result = await agent_acp_service.send_event(
            agent=sample_agent,
            event=sample_event,
            task=sample_task,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert result["status"] == "event_sent"
        assert result["event_id"] == sample_event.id

        # Verify call
        mock_http_gateway.async_call.assert_called_once()

    async def test_send_event_with_request_headers(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_event,
    ):
        """Test event sending with safe request header passthrough (not raw x-api-key)."""
        await create_or_get_agent(agent_repository, sample_agent)

        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.EVENT_SEND}-{sample_task.id}"
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "event_sent", "event_id": sample_event.id},
            "id": expected_request_id,
        }

        request_headers = {
            "x-api-key": "must-not-forward",
            "x-user-id": "user-123",
            "x-trace-id": "trace-456",
            "user-agent": "test-client",
            "authorization": "Bearer test-token",
        }

        with patch.object(
            agent_acp_service,
            "get_agent_auth_headers",
            new=AsyncMock(return_value={"x-agent-api-key": "test-api-key"}),
        ):
            result = await agent_acp_service.send_event(
                agent=sample_agent,
                event=sample_event,
                task=sample_task,
                acp_url="http://test-acp.example.com",
                request_headers=request_headers,
            )

        assert result["status"] == "event_sent"
        assert result["event_id"] == sample_event.id

        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert payload["params"]["request"] is None

        http_headers = call_args[1]["default_headers"]
        assert http_headers["x-user-id"] == "user-123"
        assert http_headers["x-trace-id"] == "trace-456"
        assert http_headers["x-agent-api-key"] == "test-api-key"
        assert "x-api-key" not in http_headers
        assert "user-agent" not in http_headers
        assert "authorization" not in http_headers

    async def test_send_event_without_request_headers(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
        sample_event,
    ):
        """Test event sending without request headers (backwards compatibility)"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock successful response
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.EVENT_SEND}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "result": {"status": "event_sent", "event_id": sample_event.id},
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When - Call without request_headers parameter
        result = await agent_acp_service.send_event(
            agent=sample_agent,
            event=sample_event,
            task=sample_task,
            acp_url="http://test-acp.example.com",
        )

        # Then
        assert result["status"] == "event_sent"
        assert result["event_id"] == sample_event.id

        # Verify call was made and request field is None when headers not provided
        mock_http_gateway.async_call.assert_called_once()
        call_args = mock_http_gateway.async_call.call_args
        payload = call_args[1]["payload"]
        assert "params" in payload
        # Request field should be None or not included when headers not provided
        if "request" in payload["params"]:
            assert payload["params"]["request"] is None

    async def test_jsonrpc_error_handling(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
    ):
        """Test JSON-RPC error response handling"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock error response
        from src.domain.entities.agents_rpc import AgentRPCMethod

        expected_request_id = f"{AgentRPCMethod.TASK_CREATE}-{sample_task.id}"
        mock_response = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": "Missing required field",
            },
            "id": expected_request_id,
        }
        mock_http_gateway.async_call.return_value = mock_response

        # When / Then
        with pytest.raises(ValueError) as exc_info:
            await agent_acp_service.create_task(
                agent=sample_agent,
                task=sample_task,
                acp_url="http://test-acp.example.com",
            )

        assert "RPC error" in str(exc_info.value)
        assert "Invalid params" in str(exc_info.value)

    async def test_http_gateway_error_handling(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        sample_task,
    ):
        """Test HTTP gateway error handling"""
        # Given - Create agent first
        await create_or_get_agent(agent_repository, sample_agent)

        # Mock HTTP error
        mock_http_gateway.async_call.side_effect = Exception("Connection timeout")

        # When / Then
        with pytest.raises(Exception) as exc_info:
            await agent_acp_service.create_task(
                agent=sample_agent,
                task=sample_task,
                acp_url="http://test-acp.example.com",
            )

        assert "Connection timeout" in str(exc_info.value)

    async def test_parse_task_message_invalid_type(self, agent_acp_service):
        """Test parsing invalid task message type"""
        # Given
        invalid_result = {
            "type": "invalid_type",
            "content": "test",
            "author": "user",
        }

        # When / Then
        with pytest.raises(ValueError) as exc_info:
            agent_acp_service._parse_task_message(invalid_result)

        assert "Unknown message type" in str(exc_info.value)

    async def test_parse_task_message_update_invalid_type(self, agent_acp_service):
        """Test parsing invalid task message update type"""
        # Given
        invalid_result = {
            "type": "invalid_update_type",
            "data": "test",
        }

        # When / Then
        with pytest.raises(ValueError) as exc_info:
            agent_acp_service._parse_task_message_update(invalid_result)

        assert "Unknown update type" in str(exc_info.value)


class _AsyncStreamMock:
    """Minimal async iterator for mocking HttpxGateway.stream_call."""

    def __init__(self, responses):
        self.responses = list(responses)
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
def task_with_metadata():
    """Task carrying caller-side metadata that is forwarded as-is to the agent."""
    return TaskEntity(
        id=str(uuid4()),
        name="task-with-meta",
        status=TaskStatus.RUNNING,
        status_reason="Test",
        task_metadata={"created_by_user_id": "user-value"},
    )


@pytest.mark.asyncio
@pytest.mark.unit
class TestACPPayloadForwardsTaskMetadata:
    """task_metadata is forwarded to the agent unchanged.

    Pre-existing agents may rely on reading task_metadata that callers set via
    PUT /tasks/{id}, so we keep the pass-through behaviour for backward
    compatibility.
    """

    async def test_create_task_payload_forwards_metadata(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        task_with_metadata,
    ):
        await create_or_get_agent(agent_repository, sample_agent)
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "created", "task_id": task_with_metadata.id},
            "id": f"AgentRPCMethod.TASK_CREATE-{task_with_metadata.id}",
        }

        await agent_acp_service.create_task(
            agent=sample_agent,
            task=task_with_metadata,
            acp_url="http://test-acp.example.com",
        )

        payload = mock_http_gateway.async_call.call_args[1]["payload"]
        assert payload["params"]["task"]["task_metadata"] == {
            "created_by_user_id": "user-value"
        }

    async def test_send_message_payload_forwards_metadata(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        task_with_metadata,
        sample_text_content,
    ):
        await create_or_get_agent(agent_repository, sample_agent)
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "type": "text",
                "author": "agent",
                "style": "static",
                "format": "plain",
                "content": "ok",
                "attachments": None,
            },
            "id": f"AgentRPCMethod.MESSAGE_SEND-{task_with_metadata.id}",
        }

        await agent_acp_service.send_message(
            agent=sample_agent,
            task=task_with_metadata,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        )

        payload = mock_http_gateway.async_call.call_args[1]["payload"]
        assert payload["params"]["task"]["task_metadata"] == {
            "created_by_user_id": "user-value"
        }

    async def test_send_message_stream_payload_forwards_metadata(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        task_with_metadata,
        sample_text_content,
    ):
        await create_or_get_agent(agent_repository, sample_agent)

        captured = {}

        def fake_stream_call(*args, **kwargs):
            captured["payload"] = kwargs.get("payload")
            return _AsyncStreamMock([])

        mock_http_gateway.stream_call = fake_stream_call

        async for _ in agent_acp_service.send_message_stream(
            agent=sample_agent,
            task=task_with_metadata,
            content=sample_text_content,
            acp_url="http://test-acp.example.com",
        ):
            pass

        payload = captured["payload"]
        assert payload["params"]["task"]["task_metadata"] == {
            "created_by_user_id": "user-value"
        }

    async def test_cancel_task_payload_forwards_metadata(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        task_with_metadata,
    ):
        await create_or_get_agent(agent_repository, sample_agent)
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "cancelled", "task_id": task_with_metadata.id},
            "id": f"AgentRPCMethod.TASK_CANCEL-{task_with_metadata.id}",
        }

        await agent_acp_service.cancel_task(
            agent=sample_agent,
            task=task_with_metadata,
            acp_url="http://test-acp.example.com",
        )

        payload = mock_http_gateway.async_call.call_args[1]["payload"]
        assert payload["params"]["task"]["task_metadata"] == {
            "created_by_user_id": "user-value"
        }

    async def test_send_event_payload_forwards_metadata(
        self,
        agent_acp_service,
        mock_http_gateway,
        agent_repository,
        sample_agent,
        task_with_metadata,
    ):
        await create_or_get_agent(agent_repository, sample_agent)
        event = EventEntity(
            id=str(uuid4()),
            task_id=task_with_metadata.id,
            agent_id=sample_agent.id,
            sequence_id=1,
            content=TextContent(content="evt", author=MessageAuthor.AGENT),
        )
        mock_http_gateway.async_call.return_value = {
            "jsonrpc": "2.0",
            "result": {"status": "event_sent", "event_id": event.id},
            "id": f"AgentRPCMethod.EVENT_SEND-{task_with_metadata.id}",
        }

        await agent_acp_service.send_event(
            agent=sample_agent,
            event=event,
            task=task_with_metadata,
            acp_url="http://test-acp.example.com",
        )

        payload = mock_http_gateway.async_call.call_args[1]["payload"]
        assert payload["params"]["task"]["task_metadata"] == {
            "created_by_user_id": "user-value"
        }


class TestFilterRequestHeaders:
    def test_blocks_user_api_key_and_acting_headers(self):
        result = filter_request_headers(
            {
                "x-api-key": "user-key",
                "x-acting-user-api-key": "spoof",
                "x-acting-as-agent": "spoof-agent",
                "x-trace-id": "trace-1",
                "authorization": "Bearer x",
            }
        )
        assert result == {"x-trace-id": "trace-1"}
