"""
Shared repository fixtures for both unit and integration tests.
Provides factory functions and specific fixtures for creating repositories with test database sessions.
"""

import pytest

# =============================================================================
# REPOSITORY FACTORY FUNCTIONS - Shared logic
# =============================================================================


def create_agent_repository(postgres_session):
    """Factory function to create AgentRepository with given PostgreSQL session"""
    from contextlib import asynccontextmanager

    from src.domain.repositories.agent_repository import AgentRepository

    # Create a session maker that returns our test session
    @asynccontextmanager
    async def session_maker():
        # The postgres_session is a direct session from the fixture
        yield postgres_session

    return AgentRepository(
        async_read_write_session_maker=session_maker,
        async_read_only_session_maker=session_maker,
    )


def create_task_repository(postgres_session):
    """Factory function to create TaskRepository with given PostgreSQL session"""
    from contextlib import asynccontextmanager

    from src.domain.repositories.task_repository import TaskRepository

    @asynccontextmanager
    async def session_maker():
        yield postgres_session

    return TaskRepository(
        async_read_write_session_maker=session_maker,
        async_read_only_session_maker=session_maker,
    )


def create_event_repository(postgres_session):
    """Factory function to create EventRepository with given PostgreSQL session"""
    from contextlib import asynccontextmanager

    from src.domain.repositories.event_repository import EventRepository

    @asynccontextmanager
    async def session_maker():
        yield postgres_session

    return EventRepository(
        async_read_write_session_maker=session_maker,
        async_read_only_session_maker=session_maker,
    )


def create_span_repository(postgres_session):
    """Factory function to create SpanRepository with given PostgreSQL session"""
    from contextlib import asynccontextmanager

    from src.domain.repositories.span_repository import SpanRepository

    @asynccontextmanager
    async def session_maker():
        yield postgres_session

    return SpanRepository(
        async_read_write_session_maker=session_maker,
        async_read_only_session_maker=session_maker,
    )


def create_task_state_repository(mongodb_database):
    """Factory function to create TaskStateRepository with given MongoDB database"""
    from src.domain.repositories.task_state_repository import TaskStateRepository

    return TaskStateRepository(db=mongodb_database)


def create_agent_api_key_repository(postgres_session):
    """Factory function to create AgentAPIKeyRepository with given PostgreSQL session"""
    from contextlib import asynccontextmanager

    from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository

    @asynccontextmanager
    async def session_maker():
        yield postgres_session

    return AgentAPIKeyRepository(
        async_read_write_session_maker=session_maker,
        async_read_only_session_maker=session_maker,
    )


def create_agent_task_tracker_repository(postgres_session):
    """Factory function to create AgentTaskTrackerRepository with given PostgreSQL session"""
    from contextlib import asynccontextmanager

    from src.domain.repositories.agent_task_tracker_repository import (
        AgentTaskTrackerRepository,
    )

    @asynccontextmanager
    async def session_maker():
        yield postgres_session

    return AgentTaskTrackerRepository(
        async_read_write_session_maker=session_maker,
        async_read_only_session_maker=session_maker,
    )


def create_task_message_repository(mongodb_database):
    """Factory function to create TaskMessageRepository with given MongoDB database"""
    from src.domain.repositories.task_message_repository import TaskMessageRepository

    return TaskMessageRepository(db=mongodb_database)


def create_redis_stream_repository(redis_client):
    """Factory function to create RedisStreamRepository with given Redis client"""
    from src.adapters.streams.adapter_redis import RedisStreamRepository

    # Create a mock environment variables object with Redis URL
    class MockEnvironmentVariables:
        def __init__(self, redis_url):
            self.REDIS_URL = redis_url
            self.REDIS_STREAM_MAXLEN = 10000  # Default from EnvironmentVariables
            self.ENVIRONMENT = "test"

    # Get the Redis URL from the client connection pool
    connection_kwargs = redis_client.connection_pool.connection_kwargs
    redis_url = f"redis://{connection_kwargs.get('host', 'localhost')}:{connection_kwargs.get('port', 6379)}"

    # Create repository with mock environment variables
    env_vars = MockEnvironmentVariables(redis_url)
    repository = RedisStreamRepository(env_vars, None)

    # Replace the Redis client with our test client
    repository.redis = redis_client

    return repository


# =============================================================================
# UNIT TEST REPOSITORY FIXTURES - Backward compatibility
# =============================================================================


@pytest.fixture
def agent_repository(unit_db_session):
    """Agent repository for unit tests"""
    return create_agent_repository(unit_db_session)


@pytest.fixture
def task_repository(unit_db_session):
    """Task repository for unit tests"""
    return create_task_repository(unit_db_session)


@pytest.fixture
def event_repository(unit_db_session):
    """Event repository for unit tests"""
    return create_event_repository(unit_db_session)


@pytest.fixture
def span_repository(unit_db_session):
    """Span repository for unit tests"""
    return create_span_repository(unit_db_session)


@pytest.fixture
def task_state_repository(unit_mongodb_database):
    """Task state repository for unit tests"""
    return create_task_state_repository(unit_mongodb_database)


@pytest.fixture
def agent_api_key_repository(unit_db_session):
    """Agent API key repository for unit tests"""
    return create_agent_api_key_repository(unit_db_session)


@pytest.fixture
def agent_task_tracker_repository(unit_db_session):
    """Agent task tracker repository for unit tests"""
    return create_agent_task_tracker_repository(unit_db_session)


@pytest.fixture
def task_message_repository(unit_mongodb_database):
    """Task message repository for unit tests"""
    return create_task_message_repository(unit_mongodb_database)


@pytest.fixture
def redis_stream_repository(unit_redis_client):
    """Redis stream repository for unit tests"""
    return create_redis_stream_repository(unit_redis_client)


# =============================================================================
# NOTE: Integration tests use REAL repositories via FastAPI dependency injection
# Only database sessions need to be overridden for test isolation
# Repository factory functions above can be used for database validation helpers
# =============================================================================
