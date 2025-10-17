import os
import time

import pytest
import redis.asyncio as redis
from pymongo import MongoClient
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(scope="session")
async def test_engine(postgres_url):
    """Create async engine for testing"""
    # Convert the testcontainers URL to asyncpg format for SQLAlchemy
    asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(asyncpg_url, echo=True)
    yield engine
    await engine.dispose()


# =============================================================================
# SHARED BASE FIXTURES - Used by both unit and integration tests
# =============================================================================


@pytest.fixture
async def base_postgres_session(postgres_session_maker):
    """
    Base PostgreSQL session with transaction rollback isolation.
    This is the shared foundation for both unit and integration tests.
    """
    async with postgres_session_maker() as session:
        transaction = await session.begin()
        try:
            yield session
        finally:
            await transaction.rollback()


@pytest.fixture
def base_mongodb_database(mongodb_connection_string):
    """
    Base MongoDB database with cleanup.
    Creates a unique database per test and cleans up afterward.
    This is the shared foundation for both unit and integration tests.
    """
    # Create unique database name with process ID for extra uniqueness
    db_name = f"test_agentex_{int(time.time() * 1000)}_{os.getpid()}"
    client = MongoClient(mongodb_connection_string)
    db = client[db_name]

    yield db

    # Cleanup: Drop the database after the test
    client.drop_database(db_name)
    client.close()


@pytest.fixture
async def base_redis_client(redis_url):
    """
    Base Redis client with cleanup.
    Creates a fresh Redis client and cleans up afterward.
    This is the shared foundation for both unit and integration tests.
    """
    client = redis.from_url(redis_url, decode_responses=False)

    yield client

    # Cleanup: Flush all data and close connection
    await client.flushall()
    await client.aclose()


# =============================================================================
# UNIT TEST ALIASES - Backward compatibility for existing unit tests
# =============================================================================


@pytest.fixture
async def unit_db_session(base_postgres_session):
    """
    Transactional session for unit tests.
    This is an alias for base_postgres_session to maintain backward compatibility.
    """
    yield base_postgres_session


@pytest.fixture
def unit_mongodb_database(base_mongodb_database):
    """
    MongoDB database for unit tests.
    This is an alias for base_mongodb_database for consistency.
    """
    yield base_mongodb_database


@pytest.fixture
async def unit_redis_client(base_redis_client):
    """
    Redis client for unit tests.
    This is an alias for base_redis_client for consistency.
    """
    yield base_redis_client


# Note: Integration tests use the same session-scoped containers directly
# The isolated_test_schema fixture in integration_client.py handles schema isolation
