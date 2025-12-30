"""
Integration test client fixture.
Uses FastAPI TestClient with minimal dependency overrides.
"""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import pymongo
import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.api.app import app, fastapi_app
from src.api.authentication_cache import reset_auth_cache
from src.config.dependencies import GlobalDependencies
from src.config.environment_variables import EnvironmentVariables


@pytest.fixture(scope="session")
def event_loop():
    """
    Session-scoped event loop to prevent "Future attached to different loop" errors.
    Based on pytest-asyncio documentation and known issues with asyncpg.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _retry_connection(coro, max_retries: int = 3, delay: float = 1.0):
    """
    Retry database connections with exponential backoff to handle container startup timing.
    """
    for attempt in range(max_retries):
        try:
            return await coro
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = delay * (2**attempt)
            print(
                f"Connection attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s..."
            )
            await asyncio.sleep(wait_time)


@pytest.fixture(scope="session")
def integration_test_db_urls(
    postgres_container,
    mongodb_container,
    redis_container,
):
    """
    Session-scoped fixture that provides database URLs from test containers.
    This only captures the connection strings, not the actual connections.
    """
    # Store original environment variables
    original_env = dict(os.environ)

    try:
        # Get database URLs from test containers
        postgres_url = postgres_container.get_connection_url()
        asyncpg_url = postgres_url.replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        mongodb_url = mongodb_container.get_connection_url()
        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"

        db_urls = {
            "postgres_url": asyncpg_url,
            "mongodb_url": mongodb_url,
            "redis_url": redis_url,
        }

        yield db_urls

    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


@pytest_asyncio.fixture
async def isolated_test_schema(integration_test_db_urls):
    """
    Function-scoped fixture that creates isolated PostgreSQL schema + MongoDB database.
    Each test gets completely isolated database environments with automatic cleanup.
    """
    # Generate unique identifiers for this test
    test_id = uuid.uuid4().hex[:12]
    schema_name = f"test_{test_id}"
    mongodb_db_name = f"agentex_test_{test_id}"

    # Create admin connection for schema management with minimal pool to reduce contention
    admin_engine = create_async_engine(
        integration_test_db_urls["postgres_url"],
        pool_pre_ping=True,
        pool_size=1,  # Minimal pool for admin operations to reduce connection conflicts
        max_overflow=0,  # No overflow connections
        pool_timeout=30,  # Longer timeout for container startup
        pool_recycle=300,  # Recycle connections to avoid stale connections
    )

    # Create MongoDB client for database management
    mongodb_client = pymongo.MongoClient(
        integration_test_db_urls["mongodb_url"],
        serverSelectionTimeoutMS=15000,  # Longer timeout for container startup
        connectTimeoutMS=10000,
    )

    # Create Redis client for test isolation
    redis_client = redis.from_url(
        integration_test_db_urls["redis_url"], decode_responses=False
    )

    schema_engine: AsyncEngine | None = None

    try:
        # Create PostgreSQL schema with retry logic
        async def create_schema():
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

        await _retry_connection(create_schema(), max_retries=3, delay=1.0)

        # Create engine for the isolated schema with proper search path
        schema_engine = create_async_engine(
            integration_test_db_urls["postgres_url"],
            pool_pre_ping=True,
            pool_size=3,  # Reduced pool size to minimize connection conflicts
            max_overflow=5,  # Reduced overflow
            pool_timeout=30,  # Longer timeout
            pool_recycle=300,
            connect_args={"server_settings": {"search_path": schema_name}},
        )

        # Create all tables in the isolated schema with retry logic
        from src.adapters.orm import BaseORM

        async def create_tables():
            async with schema_engine.begin() as conn:
                await conn.run_sync(BaseORM.metadata.create_all)

        await _retry_connection(create_tables(), max_retries=3, delay=0.5)

        # Get isolated MongoDB database
        mongodb_database = mongodb_client[mongodb_db_name]

        # Flush Redis to ensure clean state for each test
        await redis_client.flushall()

        isolation_info = {
            "test_id": test_id,
            "schema_name": schema_name,
            "mongodb_db_name": mongodb_db_name,
            "postgres_engine": schema_engine,
            "mongodb_client": mongodb_client,
            "mongodb_database": mongodb_database,
            "redis_client": redis_client,
            "admin_engine": admin_engine,
        }

        yield isolation_info

    finally:
        # Cleanup: Drop schema and MongoDB database
        try:
            # Drop PostgreSQL schema (CASCADE removes all tables)
            async def drop_schema():
                async with admin_engine.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))

            await _retry_connection(drop_schema(), max_retries=2, delay=0.5)
        except Exception as e:
            print(f"Warning: Failed to drop schema {schema_name}: {e}")

        try:
            # Drop MongoDB database
            mongodb_client.drop_database(mongodb_db_name)
        except Exception as e:
            print(f"Warning: Failed to drop MongoDB database {mongodb_db_name}: {e}")

        # Close connections with proper cleanup
        cleanup_tasks = []
        if schema_engine:
            cleanup_tasks.append(schema_engine.dispose())
        cleanup_tasks.append(admin_engine.dispose())

        try:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            mongodb_client.close()
            await redis_client.aclose()
        except Exception as e:
            print(f"Warning: Failed to cleanup connections: {e}")


@pytest.fixture
def isolated_api_key_http_client():
    """
    Fixture that provides an isolated HTTP client for API key tests.
    Uses a mock client to avoid external dependencies.
    """
    return AsyncMock(AsyncClient)


@pytest_asyncio.fixture
async def isolated_temporal_adapter():
    """
    Function-scoped fixture that provides a temporal adapter for isolated testing.
    """
    return AsyncMock(TemporalAdapter)


@pytest_asyncio.fixture
async def isolated_repositories(isolated_test_schema):
    """
    Function-scoped fixture that creates repository instances using isolated databases.
    All repositories are completely isolated per test with automatic cleanup.
    """
    # Get isolated database connections
    postgres_engine = isolated_test_schema["postgres_engine"]
    mongodb_database = isolated_test_schema["mongodb_database"]
    redis_client = isolated_test_schema["redis_client"]

    # Create read-write session factory for PostgreSQL
    async_rw_session_factory = sessionmaker(
        postgres_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create read-only session factory that enforces no writes at DB level
    # Any INSERT, UPDATE, DELETE will fail with PostgreSQL error:
    # "cannot execute X in a read-only transaction"
    class ReadOnlyAsyncSession(AsyncSession):
        """AsyncSession that sets PostgreSQL transaction to read-only mode."""

        async def __aenter__(self):
            session = await super().__aenter__()
            # Set transaction to read-only mode - PostgreSQL will reject any writes
            await session.execute(text("SET TRANSACTION READ ONLY"))
            return session

    async_ro_session_factory = sessionmaker(
        postgres_engine, class_=ReadOnlyAsyncSession, expire_on_commit=False
    )

    # Import all repository classes
    from src.adapters.streams.adapter_redis import RedisStreamRepository
    from src.domain.repositories.agent_api_key_repository import (
        AgentAPIKeyRepository,
    )
    from src.domain.repositories.agent_repository import AgentRepository
    from src.domain.repositories.agent_task_tracker_repository import (
        AgentTaskTrackerRepository,
    )
    from src.domain.repositories.deployment_history_repository import (
        DeploymentHistoryRepository,
    )
    from src.domain.repositories.event_repository import EventRepository
    from src.domain.repositories.span_repository import SpanRepository
    from src.domain.repositories.task_message_repository import TaskMessageRepository
    from src.domain.repositories.task_repository import TaskRepository
    from src.domain.repositories.task_state_repository import TaskStateRepository

    # Create Redis repository with mock environment variables
    class MockEnvironmentVariables:
        def __init__(self, redis_url):
            self.REDIS_URL = redis_url

    # Get Redis URL from client
    connection_kwargs = redis_client.connection_pool.connection_kwargs
    redis_url = f"redis://{connection_kwargs.get('host', 'localhost')}:{connection_kwargs.get('port', 6379)}"

    # Create Redis repository
    env_vars = MockEnvironmentVariables(redis_url)
    redis_stream_repository = RedisStreamRepository(env_vars, None)
    redis_stream_repository.redis = redis_client

    # Create repository instances with isolated databases
    # Read-write factory for writes, read-only factory (DB-enforced) for reads
    repositories = {
        # PostgreSQL repositories - using both rw and ro session factories
        "agent_repository": AgentRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        "agent_api_key_repository": AgentAPIKeyRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        "task_repository": TaskRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        "event_repository": EventRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        "span_repository": SpanRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        "agent_task_tracker_repository": AgentTaskTrackerRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        "deployment_history_repository": DeploymentHistoryRepository(
            async_rw_session_factory, async_ro_session_factory
        ),
        # MongoDB repositories
        "task_message_repository": TaskMessageRepository(mongodb_database),
        "task_state_repository": TaskStateRepository(mongodb_database),
        # Redis repositories
        "redis_stream_repository": redis_stream_repository,
        # Direct access for advanced use cases
        "postgres_rw_session_factory": async_rw_session_factory,
        "postgres_ro_session_factory": async_ro_session_factory,
        "postgres_engine": postgres_engine,
        "mongodb_database": mongodb_database,
        "mongodb_client": isolated_test_schema["mongodb_client"],
        "redis_client": redis_client,
        "test_id": isolated_test_schema["test_id"],
    }

    yield repositories


@pytest_asyncio.fixture
async def isolated_integration_app(
    isolated_repositories, isolated_api_key_http_client, isolated_temporal_adapter
):
    """
    Function-scoped fixture that provides FastAPI app with completely isolated dependencies.
    All use cases get repositories that point to isolated test databases.
    """
    # Set dummy environment variables (we override dependencies anyway)
    os.environ.update(
        {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "MONGODB_URI": "mongodb://test:test@localhost:27017",
            "MONGODB_DATABASE_NAME": "agentex_test",
            "TEMPORAL_ADDRESS": "false",  # Skip Temporal for tests
            "REDIS_URL": "redis://localhost:6379",  # Mock Redis
        }
    )

    # Clear any cached dependencies
    await reset_auth_cache()
    EnvironmentVariables.clear_cache()
    GlobalDependencies._instances = {}

    # Configure GlobalDependencies singleton with test container connections
    # This is required for HealthCheckInterceptor which directly accesses GlobalDependencies
    deps = GlobalDependencies()
    deps.database_async_read_write_engine = isolated_repositories["postgres_engine"]
    deps.database_async_read_only_engine = isolated_repositories["postgres_engine"]
    deps.mongodb_client = isolated_repositories["mongodb_client"]
    deps.mongodb_database = isolated_repositories["mongodb_database"]
    deps.redis_pool = isolated_repositories["redis_client"].connection_pool
    deps._loaded = True

    # Import use case classes we can properly create with direct repositories
    from src.domain.use_cases.agent_api_keys_use_case import AgentAPIKeysUseCase
    from src.domain.use_cases.agent_task_tracker_use_case import AgentTaskTrackerUseCase
    from src.domain.use_cases.agents_use_case import AgentsUseCase
    from src.domain.use_cases.deployment_history_use_case import (
        DeploymentHistoryUseCase,
    )
    from src.domain.use_cases.events_use_case import EventUseCase
    from src.domain.use_cases.messages_use_case import MessagesUseCase
    from src.domain.use_cases.spans_use_case import SpanUseCase
    from src.domain.use_cases.states_use_case import StatesUseCase
    from src.domain.use_cases.tasks_use_case import TasksUseCase

    # Create use case factory functions with isolated repositories
    def create_agents_use_case():
        return AgentsUseCase(
            agent_repository=isolated_repositories["agent_repository"],
            temporal_adapter=isolated_temporal_adapter,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
        )

    def create_agent_api_keys_use_case():
        return AgentAPIKeysUseCase(
            agent_api_key_repository=isolated_repositories["agent_api_key_repository"],
            agent_repository=isolated_repositories["agent_repository"],
            client=isolated_api_key_http_client,  # Use mock client for forwarding requests
        )

    def create_deployment_history_use_case():
        return DeploymentHistoryUseCase(
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ]
        )

    def create_events_use_case():
        return EventUseCase(event_repository=isolated_repositories["event_repository"])

    def create_spans_use_case():
        return SpanUseCase(span_repository=isolated_repositories["span_repository"])

    def create_states_use_case():
        return StatesUseCase(
            task_state_repository=isolated_repositories["task_state_repository"]
        )

    def create_agent_task_tracker_use_case():
        return AgentTaskTrackerUseCase(
            tracker_repository=isolated_repositories["agent_task_tracker_repository"]
        )

    def create_tasks_use_case():
        """Create a TasksUseCase with real AgentTaskService for comprehensive testing"""
        from src.domain.services.task_service import AgentTaskService

        # Mock ACP service to avoid external dependencies
        class MockAgentACPService:
            async def cancel_task(self, *args, **kwargs):
                pass

            async def send_event(self, *args, **kwargs):
                pass

            async def send_message(self, *args, **kwargs):
                pass

        task_service = AgentTaskService(
            acp_client=MockAgentACPService(),
            task_state_repository=isolated_repositories["task_state_repository"],
            task_repository=isolated_repositories["task_repository"],
            event_repository=isolated_repositories["event_repository"],
            stream_repository=isolated_repositories["redis_stream_repository"],
        )

        return TasksUseCase(task_service=task_service)

    def create_messages_use_case():
        """Create MessagesUseCase for comprehensive testing"""
        from src.domain.services.task_message_service import TaskMessageService

        task_message_service = TaskMessageService(
            message_repository=isolated_repositories["task_message_repository"]
        )

        return MessagesUseCase(task_message_service=task_message_service)

    # Import dependency types and repository classes that need to be overridden
    from src.adapters.streams.adapter_redis import RedisStreamRepository
    from src.config.dependencies import (
        DDatabaseAsyncReadOnlySessionMaker,
        DDatabaseAsyncReadWriteSessionMaker,
        DMongoDBDatabase,
    )
    from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
    from src.domain.repositories.agent_repository import AgentRepository
    from src.domain.repositories.agent_task_tracker_repository import (
        AgentTaskTrackerRepository,
    )
    from src.domain.repositories.deployment_history_repository import (
        DeploymentHistoryRepository,
    )
    from src.domain.repositories.event_repository import EventRepository
    from src.domain.repositories.span_repository import SpanRepository
    from src.domain.repositories.task_message_repository import TaskMessageRepository
    from src.domain.repositories.task_repository import TaskRepository
    from src.domain.repositories.task_state_repository import TaskStateRepository

    # Override use cases AND core dependencies with isolated versions
    # Note: We use fastapi_app (not app) because app is the HealthCheckInterceptor wrapper
    fastapi_app.dependency_overrides.update(
        {
            # Core dependencies - these must be overridden for isolation to work
            DMongoDBDatabase: lambda: isolated_repositories["mongodb_database"],
            DDatabaseAsyncReadWriteSessionMaker: lambda: isolated_repositories[
                "postgres_rw_session_factory"
            ],
            DDatabaseAsyncReadOnlySessionMaker: lambda: isolated_repositories[
                "postgres_ro_session_factory"
            ],
            # Use cases
            AgentsUseCase: create_agents_use_case,
            EventUseCase: create_events_use_case,
            SpanUseCase: create_spans_use_case,
            StatesUseCase: create_states_use_case,
            AgentTaskTrackerUseCase: create_agent_task_tracker_use_case,
            TasksUseCase: create_tasks_use_case,
            MessagesUseCase: create_messages_use_case,
            AgentAPIKeysUseCase: create_agent_api_keys_use_case,
            DeploymentHistoryUseCase: create_deployment_history_use_case,
            # Repositories - these ensure consistent isolated instances
            TaskStateRepository: lambda: isolated_repositories["task_state_repository"],
            TaskMessageRepository: lambda: isolated_repositories[
                "task_message_repository"
            ],
            AgentRepository: lambda: isolated_repositories["agent_repository"],
            AgentAPIKeyRepository: lambda: isolated_repositories[
                "agent_api_key_repository"
            ],
            TaskRepository: lambda: isolated_repositories["task_repository"],
            EventRepository: lambda: isolated_repositories["event_repository"],
            SpanRepository: lambda: isolated_repositories["span_repository"],
            AgentTaskTrackerRepository: lambda: isolated_repositories[
                "agent_task_tracker_repository"
            ],
            DeploymentHistoryRepository: lambda: isolated_repositories[
                "deployment_history_repository"
            ],
            # Redis repositories
            RedisStreamRepository: lambda: isolated_repositories[
                "redis_stream_repository"
            ],
        }
    )

    try:
        # Return the wrapped app (HealthCheckInterceptor) for realistic testing
        yield app
    finally:
        # Clear dependency overrides on the FastAPI instance
        fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def isolated_client(isolated_integration_app):
    """
    Function-scoped fixture that provides httpx.AsyncClient for isolated testing.
    Each test gets a completely isolated HTTP client with isolated databases.
    """
    async with AsyncClient(
        transport=ASGITransport(app=isolated_integration_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """
    Ensures dependency overrides are cleared before and after each test.
    This prevents test interference at the FastAPI level.
    """
    fastapi_app.dependency_overrides.clear()
    yield
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def isolated_db_session(isolated_repositories):
    """
    Function-scoped fixture that provides direct database session access.
    Useful for test setup/verification that needs direct database access.
    """
    async with isolated_repositories["postgres_rw_session_factory"]() as session:
        yield session


@pytest_asyncio.fixture
async def test_data_factory(isolated_repositories):
    """
    Function-scoped fixture that provides a factory for creating test data.
    Uses the test_id to ensure data is unique and traceable.
    """
    test_id = isolated_repositories["test_id"]

    def create_unique_name(base_name: str) -> str:
        """Create a unique name for test data (use hyphens for API compatibility)"""
        return f"{base_name}-{test_id}"

    def create_agent_data(name: str = "test-agent") -> dict:
        """Create unique agent test data"""
        return {
            "name": create_unique_name(name),
            "description": f"Test agent for {test_id}",
            "acp_url": f"http://{create_unique_name('test')}:8000",
            "acp_type": "sync",
        }

    def create_task_data(name: str = "test-task", agent_id: str = None) -> dict:
        """Create unique task test data"""
        return {
            "name": create_unique_name(name),
            "agent_id": agent_id,
        }

    def create_state_data(task_id: str, agent_id: str, state: dict = None) -> dict:
        """Create unique state test data"""
        return {
            "task_id": task_id,
            "agent_id": agent_id,
            "state": state or {"status": "test", "test_id": test_id},
        }

    factory = {
        "test_id": test_id,
        "create_unique_name": create_unique_name,
        "create_agent_data": create_agent_data,
        "create_task_data": create_task_data,
        "create_state_data": create_state_data,
    }

    yield factory
