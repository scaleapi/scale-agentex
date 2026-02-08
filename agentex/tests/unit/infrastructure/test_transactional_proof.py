import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
@pytest.mark.unit
async def test_transactional_rollback_proof(postgres_url):
    """Prove that transactional rollback actually works"""
    # Convert URL for SQLAlchemy async
    asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(asyncpg_url, echo=True)

    try:
        # First, verify the table is empty
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS test_rollback (id SERIAL PRIMARY KEY, name TEXT)"
                )
            )
            await conn.execute(text("DELETE FROM test_rollback"))  # Ensure clean slate

        # Test 1: Verify normal commit works
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO test_rollback (name) VALUES ('committed-record')")
            )
            # Transaction commits automatically at end of `async with`

        # Verify the committed record exists
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
            assert result.scalar() == 1

        # Test 2: Verify rollback works
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("INSERT INTO test_rollback (name) VALUES ('should-rollback')")
                )
                # Should have 2 records now
                result = await conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
                assert result.scalar() == 2

                # Force a rollback by raising an exception
                raise Exception("Force rollback")
        except Exception as e:
            if "Force rollback" not in str(e):
                raise

        # Test 3: Verify the rollback actually happened
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
            count = result.scalar()
            assert count == 1, f"Expected 1 record after rollback, got {count}"

        print("✅ TRANSACTIONAL ROLLBACK PROOF SUCCESSFUL")

    finally:
        await engine.dispose()
