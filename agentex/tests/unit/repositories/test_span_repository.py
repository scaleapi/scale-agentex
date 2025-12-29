import asyncio
import os

# Import the repository and entities we need to test
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from adapters.orm import BaseORM
from domain.entities.spans import SpanEntity
from domain.repositories.span_repository import SpanRepository
from utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_span_repository_crud_operations(postgres_url):
    """Test SpanRepository CRUD operations with JSON fields and time ordering"""

    # URL conversion for SQLAlchemy async
    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    # Wait for database readiness
    for attempt in range(10):
        try:
            engine = create_async_engine(sqlalchemy_asyncpg_url, echo=True)
            async with engine.begin() as conn:
                await conn.run_sync(BaseORM.metadata.create_all)
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

    # Create async session maker and repository
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    span_repo = SpanRepository(async_session_maker, async_session_maker)

    # Test CREATE operation with JSON fields
    now = datetime.now(UTC)
    span_id = orm_id()
    trace_id = orm_id()

    span = SpanEntity(
        id=span_id,
        trace_id=trace_id,
        parent_id=None,
        name="test-span-operation",
        start_time=now,
        end_time=None,  # Still running
        input={"operation": "test", "parameters": {"limit": 10}},
        output=None,  # Not finished yet
        data={"metadata": {"version": "1.0", "environment": "test"}},
    )

    created_span = await span_repo.create(span)
    assert created_span.id == span_id
    assert created_span.trace_id == trace_id
    assert created_span.name == "test-span-operation"
    assert created_span.input["operation"] == "test"
    assert created_span.data["metadata"]["version"] == "1.0"
    print("✅ CREATE operation successful with JSON fields")

    # Test UPDATE operation (complete the span)
    end_time = datetime.now(UTC)
    updated_span = SpanEntity(
        id=span_id,
        trace_id=trace_id,
        parent_id=None,
        name="test-span-operation",
        start_time=now,
        end_time=end_time,
        input={"operation": "test", "parameters": {"limit": 10}},
        output={"result": "success", "processed": 5},
        data={
            "metadata": {"version": "1.0", "environment": "test", "duration_ms": 150}
        },
    )

    result_span = await span_repo.update(updated_span)
    assert result_span.end_time is not None
    assert result_span.output["result"] == "success"
    assert result_span.data["metadata"]["duration_ms"] == 150
    print("✅ UPDATE operation successful")

    # Test GET operation
    retrieved_span = await span_repo.get(id=span_id)
    assert retrieved_span.id == span_id
    assert retrieved_span.output["processed"] == 5
    print("✅ GET operation successful")

    # Create a child span to test ordering
    child_span_id = orm_id()
    child_start_time = datetime.now(UTC)

    child_span = SpanEntity(
        id=child_span_id,
        trace_id=trace_id,
        parent_id=span_id,  # Child of the first span
        name="child-span-operation",
        start_time=child_start_time,
        end_time=None,
        input={"operation": "child_task"},
        output=None,
        data={"parent_context": "inherited"},
    )

    await span_repo.create(child_span)
    print("✅ Child span created for ordering test")

    # Test LIST operation with time-based ordering
    all_spans = await span_repo.list()
    assert len(all_spans) >= 2
    span_ids = [s.id for s in all_spans]
    assert span_id in span_ids
    assert child_span_id in span_ids

    # Should be ordered by start_time (parent should come first)
    parent_index = next(i for i, s in enumerate(all_spans) if s.id == span_id)
    child_index = next(i for i, s in enumerate(all_spans) if s.id == child_span_id)
    assert parent_index < child_index, "Parent span should come before child span"
    print("✅ LIST operation successful with time ordering")

    # Test DELETE operation
    await span_repo.delete(child_span_id)

    # Verify deletion
    all_spans_after_delete = await span_repo.list()
    span_ids_after_delete = [s.id for s in all_spans_after_delete]
    assert child_span_id not in span_ids_after_delete
    assert span_id in span_ids_after_delete
    print("✅ DELETE operation successful")

    print("✅ Test isolation provided by session-scoped PostgreSQL container")
    print("🎉 ALL SPAN REPOSITORY TESTS PASSED!")
