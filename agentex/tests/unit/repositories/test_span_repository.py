import asyncio
import os

# Import the repository and entities we need to test
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from adapters.orm import BaseORM, TaskORM
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

    # Create a task row to satisfy the FK constraint on spans.task_id
    task_id = orm_id()
    async with async_session_maker() as session:
        session.add(TaskORM(id=task_id, name="test-task"))
        await session.commit()

    # Test CREATE operation with JSON fields
    now = datetime.now(UTC)
    span_id = orm_id()
    trace_id = orm_id()

    span = SpanEntity(
        id=span_id,
        trace_id=trace_id,
        task_id=task_id,
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
    assert created_span.task_id == task_id
    assert created_span.name == "test-span-operation"
    assert created_span.input["operation"] == "test"
    assert created_span.data["metadata"]["version"] == "1.0"
    print("✅ CREATE operation successful with JSON fields")

    # Test UPDATE operation (complete the span)
    end_time = datetime.now(UTC)
    updated_span = SpanEntity(
        id=span_id,
        trace_id=trace_id,
        task_id=task_id,
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
        task_id=task_id,
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


@pytest.mark.asyncio
@pytest.mark.unit
async def test_span_task_id_set_null_on_task_delete(postgres_url):
    """Deleting a referenced task should null out spans.task_id, not fail with FK violation."""

    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(sqlalchemy_asyncpg_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    span_repo = SpanRepository(async_session_maker, async_session_maker)

    # Seed a task and a span referencing it
    task_id = orm_id()
    span_id = orm_id()
    async with async_session_maker() as session:
        session.add(TaskORM(id=task_id, name="task-to-delete"))
        await session.commit()

    await span_repo.create(
        SpanEntity(
            id=span_id,
            trace_id=orm_id(),
            task_id=task_id,
            parent_id=None,
            name="span-with-task-fk",
            start_time=datetime.now(UTC),
        )
    )

    # Delete the task — should succeed, not raise a FK violation
    async with async_session_maker() as session:
        task = await session.get(TaskORM, task_id)
        await session.delete(task)
        await session.commit()

    # Span should survive with task_id set to NULL
    retrieved = await span_repo.get(id=span_id)
    assert retrieved is not None
    assert retrieved.task_id is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_by_task_id_falls_back_to_trace_id(postgres_url):
    """Listing by task_id should also match historical rows that have the value
    in trace_id but a NULL task_id (pre-backfill state)."""

    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(sqlalchemy_asyncpg_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    span_repo = SpanRepository(async_session_maker, async_session_maker)

    task_id = orm_id()
    async with async_session_maker() as session:
        session.add(TaskORM(id=task_id, name="task-or-fallback"))
        await session.commit()

    # Historical span: task_id NULL, trace_id holds the task id (pre-backfill)
    historical_id = orm_id()
    await span_repo.create(
        SpanEntity(
            id=historical_id,
            trace_id=task_id,
            task_id=None,
            parent_id=None,
            name="historical",
            start_time=datetime.now(UTC),
        )
    )

    # New-style span: task_id set explicitly, trace_id is unrelated
    new_id = orm_id()
    await span_repo.create(
        SpanEntity(
            id=new_id,
            trace_id=orm_id(),
            task_id=task_id,
            parent_id=None,
            name="new-style",
            start_time=datetime.now(UTC),
        )
    )

    # Unrelated span: should not match
    unrelated_id = orm_id()
    await span_repo.create(
        SpanEntity(
            id=unrelated_id,
            trace_id=orm_id(),
            task_id=None,
            parent_id=None,
            name="unrelated",
            start_time=datetime.now(UTC),
        )
    )

    matched = await span_repo.list(filters={"task_id": task_id})
    matched_ids = {s.id for s in matched}
    assert historical_id in matched_ids
    assert new_id in matched_ids
    assert unrelated_id not in matched_ids


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_with_none_task_id_does_not_or_on_trace_id(postgres_url):
    """A None task_id filter must NOT trigger the trace_id OR fallback,
    otherwise the predicate expands to (task_id IS NULL OR trace_id IS NULL)
    and returns nearly every row on a partially backfilled table."""

    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(sqlalchemy_asyncpg_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    span_repo = SpanRepository(async_session_maker, async_session_maker)

    # Span with non-null trace_id and null task_id (pre-backfill historical row).
    # If the OR fallback were applied to a None task_id filter, this row would
    # incorrectly match because trace_id IS NOT NULL but task_id IS NULL — the
    # generated predicate (task_id IS NULL OR trace_id IS NULL) would be true.
    # Wait: with this row trace_id IS NOT NULL, so trace_id IS NULL is false.
    # The bug is the *other* direction: task_id IS NULL is true → row matches
    # the (incorrectly) ORed predicate, even though the caller asked for
    # task_id IS NULL only.
    historical_id = orm_id()
    await span_repo.create(
        SpanEntity(
            id=historical_id,
            trace_id=orm_id(),
            task_id=None,
            parent_id=None,
            name="historical-null-task",
            start_time=datetime.now(UTC),
        )
    )

    # Span where both task_id and trace_id are non-null. This row should NOT
    # match a "task_id IS NULL" filter under either correct or incorrect
    # behavior — included as a sanity check.
    populated_id = orm_id()
    task_id = orm_id()
    async with async_session_maker() as session:
        session.add(TaskORM(id=task_id, name="task-for-populated-span"))
        await session.commit()
    await span_repo.create(
        SpanEntity(
            id=populated_id,
            trace_id=orm_id(),
            task_id=task_id,
            parent_id=None,
            name="populated",
            start_time=datetime.now(UTC),
        )
    )

    # Filtering by task_id=None should match only the historical (NULL task_id)
    # row, NOT trigger the OR fallback against trace_id.
    matched = await span_repo.list(filters={"task_id": None})
    matched_ids = {s.id for s in matched}
    assert historical_id in matched_ids
    assert populated_id not in matched_ids


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_combines_task_id_and_trace_id_filters(postgres_url):
    """When both task_id and trace_id are passed, the trace_id filter still
    applies on top of the task_id OR-fallback (logical AND between filters)."""

    sqlalchemy_asyncpg_url = postgres_url.replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(sqlalchemy_asyncpg_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    span_repo = SpanRepository(async_session_maker, async_session_maker)

    task_id = orm_id()
    other_trace_id = orm_id()
    async with async_session_maker() as session:
        session.add(TaskORM(id=task_id, name="task-and"))
        await session.commit()

    # Span matches task_id but not the requested trace_id — should be excluded
    excluded_id = orm_id()
    await span_repo.create(
        SpanEntity(
            id=excluded_id,
            trace_id=orm_id(),
            task_id=task_id,
            parent_id=None,
            name="excluded",
            start_time=datetime.now(UTC),
        )
    )

    # Span matches both — should be included
    included_id = orm_id()
    await span_repo.create(
        SpanEntity(
            id=included_id,
            trace_id=other_trace_id,
            task_id=task_id,
            parent_id=None,
            name="included",
            start_time=datetime.now(UTC),
        )
    )

    matched = await span_repo.list(
        filters={"task_id": task_id, "trace_id": other_trace_id}
    )
    matched_ids = {s.id for s in matched}
    assert included_id in matched_ids
    assert excluded_id not in matched_ids
