from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.task_messages import TextContent
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.events import EventEntity
from src.domain.entities.task_messages import (
    MessageAuthor,
    MessageStyle,
    TextContentEntity,
    TextFormat,
)
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.services.agent_acp_service import AgentACPService

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
    return AgentRepository(postgres_session_maker)


@pytest.fixture
def agent_api_key_repository(postgres_session_maker):
    """Real AgentAPIKeyRepository using test PostgreSQL database"""
    return AgentAPIKeyRepository(postgres_session_maker)


@pytest.fixture
def agent_acp_service(mock_http_gateway, agent_repository, agent_api_key_repository):
    """Create AgentACPService instance with mocked HTTP gateway and real repository"""
    return AgentACPService(
        http_gateway=mock_http_gateway,
        agent_repository=agent_repository,
        agent_api_key_repository=agent_api_key_repository,
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for ACP service testing",
        acp_type=ACPType.AGENTIC,
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
