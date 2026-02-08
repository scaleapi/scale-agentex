import time

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.unit
def test_sync_transactional_rollback_proof(postgres_url):
    """Prove that transactional rollback works with sync SQLAlchemy"""
    # Use sync psycopg2 connection (already in correct format)
    engine = create_engine(postgres_url, echo=True)

    # Wait a bit for PostgreSQL to be fully ready
    time.sleep(2)

    try:
        # First, set up clean test table
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_rollback"))
            conn.execute(
                text("CREATE TABLE test_rollback (id SERIAL PRIMARY KEY, name TEXT)")
            )

        # Test 1: Verify normal commit works
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO test_rollback (name) VALUES ('committed-record')")
            )
            # Transaction commits automatically

        # Verify the committed record exists
        with engine.begin() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
            assert result.scalar() == 1

        # Test 2: Verify rollback works
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO test_rollback (name) VALUES ('should-rollback')")
                )
                # Should have 2 records now
                result = conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
                assert result.scalar() == 2

                # Force a rollback by raising an exception
                raise Exception("Force rollback")
        except Exception as e:
            if "Force rollback" not in str(e):
                raise

        # Test 3: Verify the rollback actually happened
        with engine.begin() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM test_rollback"))
            count = result.scalar()
            assert count == 1, f"Expected 1 record after rollback, got {count}"

        print("✅ SYNC TRANSACTIONAL ROLLBACK PROOF SUCCESSFUL")

    finally:
        engine.dispose()
