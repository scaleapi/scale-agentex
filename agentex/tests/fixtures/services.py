"""
Shared service fixtures for both unit and integration tests.
Provides factory functions and specific fixtures for creating services with test repositories.
"""

from unittest.mock import Mock

import pytest

# =============================================================================
# SERVICE FACTORY FUNCTIONS - Shared logic
# =============================================================================


def create_task_message_service(task_message_repository):
    """Factory function to create TaskMessageService with given repository"""
    from src.domain.services.task_message_service import TaskMessageService

    return TaskMessageService(task_message_repository=task_message_repository)


def create_agent_acp_service(http_gateway, agent_repository, agent_api_key_repository):
    """Factory function to create AgentACPService with given HTTP gateway"""
    from src.domain.services.agent_acp_service import AgentACPService

    return AgentACPService(
        http_gateway=http_gateway,
        agent_repository=agent_repository,
        agent_api_key_repository=agent_api_key_repository,
    )


def create_task_service(
    task_repository,
    event_repository,
    agent_acp_service,
    redis_stream_repository,
):
    """Factory function to create AgentTaskService with given repositories and services"""
    from src.domain.services.task_service import AgentTaskService

    return AgentTaskService(
        task_repository=task_repository,
        event_repository=event_repository,
        acp_client=agent_acp_service,
        stream_repository=redis_stream_repository,
    )


# =============================================================================
# MOCK FACTORIES - Shared mocks
# =============================================================================


def create_mock_http_gateway():
    """Factory function to create a mock HTTP gateway"""
    mock = Mock()

    # Default successful async_call response
    mock.async_call.return_value = {
        "jsonrpc": "2.0",
        "result": {"status": "success"},
        "id": "test-request",
    }

    # Default successful stream_call response
    mock.stream_call.return_value = Mock()

    return mock


def create_mock_temporal_client():
    """Factory function to create a mock Temporal client"""
    return Mock()


def create_mock_environment_variables():
    """Factory function to create mock environment variables"""
    mock = Mock()
    mock.TEMPORAL_ADDRESS = "mock://temporal"
    mock.DATABASE_URL = "mock://postgres"
    mock.MONGODB_URI = "mock://mongodb"
    mock.MONGODB_DATABASE_NAME = "test_db"
    return mock


# =============================================================================
# UNIT TEST SERVICE FIXTURES - Backward compatibility
# =============================================================================


@pytest.fixture
def mock_http_gateway():
    """Mock HTTP gateway for unit tests"""
    return create_mock_http_gateway()


@pytest.fixture
def mock_temporal_client():
    """Mock Temporal client for unit tests"""
    return create_mock_temporal_client()


@pytest.fixture
def mock_environment_variables():
    """Mock environment variables for unit tests"""
    return create_mock_environment_variables()


@pytest.fixture
def task_message_service(task_message_repository):
    """Task message service for unit tests"""
    return create_task_message_service(task_message_repository)


@pytest.fixture
def agent_acp_service(mock_http_gateway, agent_repository, agent_api_key_repository):
    """Agent ACP service for unit tests"""
    return create_agent_acp_service(
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
    """Task service for unit tests"""
    return create_task_service(
        task_repository,
        event_repository,
        agent_acp_service,
        redis_stream_repository,
    )


# =============================================================================
# NOTE: Integration tests use REAL services via FastAPI dependency injection
# No separate integration service fixtures needed - TestClient uses real app stack
# =============================================================================
