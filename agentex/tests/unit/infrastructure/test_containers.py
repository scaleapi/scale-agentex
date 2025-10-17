import asyncpg
import pytest


@pytest.mark.asyncio
@pytest.mark.unit
async def test_postgres_container_works(postgres_url):
    """Test that PostgreSQL container starts and accepts connections"""
    # Convert SQLAlchemy URL to asyncpg URL (remove +psycopg2 part)
    asyncpg_url = postgres_url.replace("postgresql+psycopg2://", "postgresql://")

    conn = await asyncpg.connect(asyncpg_url)
    result = await conn.fetchval("SELECT 1")
    await conn.close()
    assert result == 1
