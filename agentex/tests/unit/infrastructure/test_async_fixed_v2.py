import asyncio

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_transactional_rollback_fixed(postgres_url):
    """Test async transactional rollback with correct URL handling"""

    # For direct asyncpg connection: just remove +psycopg2
    direct_asyncpg_url = postgres_url.replace("postgresql+psycopg2://", "postgresql://")

    # For SQLAlchemy async engine: replace with +asyncpg
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Add retry logic for container readiness
    max_retries = 10
    retry_delay = 1

    print(f"Testing with direct asyncpg URL: {direct_asyncpg_url}")
    print(f"Testing with SQLAlchemy URL: {sqlalchemy_asyncpg_url}")

    for attempt in range(max_retries):
        try:
            # Test basic asyncpg connection first
            conn = await asyncpg.connect(direct_asyncpg_url)
            await conn.fetchval("SELECT 1")
            await conn.close()
            print(f"✅ PostgreSQL ready after {attempt + 1} attempts")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(
                    f"PostgreSQL not ready after {max_retries} attempts: {e}"
                ) from e
            print(f"⏳ Attempt {attempt + 1}: PostgreSQL not ready, waiting...")
            await asyncio.sleep(retry_delay)

    # Now test with SQLAlchemy async engine
    engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)

    try:
        # Test 1: Set up clean test table
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS test_async_rollback"))
            await conn.execute(
                text(
                    "CREATE TABLE test_async_rollback (id SERIAL PRIMARY KEY, name TEXT)"
                )
            )

        # Test 2: Verify normal commit works
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO test_async_rollback (name) VALUES ('async-committed')"
                )
            )
            # Transaction commits automatically

        # Verify the committed record exists
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM test_async_rollback")
            )
            assert result.scalar() == 1

        # Test 3: Verify rollback works
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO test_async_rollback (name) VALUES ('should-async-rollback')"
                    )
                )
                # Should have 2 records now
                result = await conn.execute(
                    text("SELECT COUNT(*) FROM test_async_rollback")
                )
                assert result.scalar() == 2

                # Force a rollback by raising an exception
                raise Exception("Force async rollback")
        except Exception as e:
            if "Force async rollback" not in str(e):
                raise

        # Test 4: Verify the rollback actually happened
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM test_async_rollback")
            )
            count = result.scalar()
            assert count == 1, f"Expected 1 record after async rollback, got {count}"

        print("✅ ASYNC TRANSACTIONAL ROLLBACK PROOF SUCCESSFUL")

    finally:
        await engine.dispose()
