import asyncio
import time

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.mongodb import MongoDbContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Single PostgreSQL container for testing with improved stability"""
    with PostgresContainer("postgres:17") as container:
        # Wait a bit for PostgreSQL to be fully ready
        time.sleep(3)
        yield container


@pytest.fixture(scope="session")
def postgres_url(postgres_container):
    """Get PostgreSQL connection URL"""
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def mongodb_container():
    """
    Session-scoped MongoDB container using testcontainers with improved stability.
    Provides a clean MongoDB instance for the entire test session.
    """
    with MongoDbContainer("mongo:6.0") as container:
        # Wait for MongoDB to be ready
        time.sleep(3)

        # Verify MongoDB is responding
        max_retries = 5
        for attempt in range(max_retries):
            try:
                import pymongo

                client = pymongo.MongoClient(
                    container.get_connection_url(),
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                )
                # Test the connection
                client.admin.command("ping")
                client.close()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Warning: MongoDB container not fully ready: {e}")
                time.sleep(1)

        yield container


@pytest.fixture(scope="session")
def mongodb_connection_string(mongodb_container):
    """
    Session-scoped MongoDB connection string.
    """
    return mongodb_container.get_connection_url()


@pytest.fixture
def mongodb_database(mongodb_connection_string):
    """
    Function-scoped MongoDB database instance.
    Creates a fresh database for each test to ensure isolation.
    """
    import time

    from pymongo import MongoClient

    # Create a unique database name for this test
    db_name = f"test_agentex_{int(time.time() * 1000)}"
    client = MongoClient(mongodb_connection_string)
    db = client[db_name]

    yield db

    # Cleanup: Drop the database after the test
    client.drop_database(db_name)
    client.close()


@pytest.fixture(scope="session")
def redis_container():
    """Single Redis container for testing with improved stability"""
    with RedisContainer("redis:7.4.0-alpine") as container:
        # Wait a bit for Redis to be fully ready
        time.sleep(2)
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container):
    """Get Redis connection URL"""
    return f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"


@pytest_asyncio.fixture
async def postgres_session_maker(postgres_url):
    """
    Function-scoped PostgreSQL async session maker.
    Creates a fresh session maker for each test to ensure isolation.
    """
    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness and create tables
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=False)
            async with engine.begin() as conn:
                # Import and create all tables
                import os
                import sys

                sys.path.append(
                    os.path.join(os.path.dirname(__file__), "..", "..", "src")
                )
                from adapters.orm import BaseORM

                await conn.run_sync(BaseORM.metadata.create_all)
                # Test connectivity
                await conn.execute(text("SELECT 1"))
            break
        except Exception as e:
            if attempt < 9:
                print(
                    f"Database not ready (attempt {attempt + 1}), retrying... Error: {e}"
                )
                await asyncio.sleep(2)
                continue
            raise

    # Create async session maker
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    yield async_session_maker

    # Cleanup
    await engine.dispose()
