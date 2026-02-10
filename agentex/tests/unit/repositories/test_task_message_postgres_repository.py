"""
Unit tests for TaskMessagePostgresRepository filter translation.

These tests verify the JSONB filter conversion logic that translates
TaskMessageEntityFilter objects into SQLAlchemy WHERE clauses.
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from domain.entities.task_messages import (
    MessageAuthor,
    OptionalDataContentEntity,
    OptionalTextContentEntity,
    TaskMessageContentType,
    TaskMessageEntityFilter,
)
from domain.repositories.task_message_postgres_repository import (
    _build_jsonb_clause,
    _flatten_to_dot_path,
    convert_filters_to_postgres_clauses,
)


@pytest.mark.unit
class TestFlattenToDotPath:
    """Tests for dot-path flattening utility."""

    def test_flat_dict(self):
        result = _flatten_to_dot_path({"type": "text"})
        assert result == {"type": "text"}

    def test_nested_dict(self):
        result = _flatten_to_dot_path({"content": {"type": "text"}})
        assert result == {"content.type": "text"}

    def test_deeply_nested_dict(self):
        result = _flatten_to_dot_path({"content": {"data": {"type": "metrics"}}})
        assert result == {"content.data.type": "metrics"}

    def test_multiple_keys(self):
        result = _flatten_to_dot_path({"content": {"type": "text", "author": "user"}})
        assert result == {"content.type": "text", "content.author": "user"}

    def test_empty_dict(self):
        result = _flatten_to_dot_path({})
        assert result == {}


@pytest.mark.unit
class TestBuildJsonbClause:
    """Tests for JSONB clause builder."""

    def test_content_type_clause(self):
        clause = _build_jsonb_clause("content.type", "text")
        assert clause is not None
        # Verify it creates a proper SQLAlchemy expression
        assert str(clause.compile(compile_kwargs={"literal_binds": True}))

    def test_content_author_clause(self):
        clause = _build_jsonb_clause("content.author", "user")
        assert clause is not None

    def test_deeply_nested_clause(self):
        clause = _build_jsonb_clause("content.data.type", "metrics")
        assert clause is not None

    def test_streaming_status_clause(self):
        clause = _build_jsonb_clause("streaming_status", "IN_PROGRESS")
        assert clause is not None

    def test_unknown_field_returns_none(self):
        clause = _build_jsonb_clause("nonexistent.field", "value")
        assert clause is None


@pytest.mark.unit
class TestConvertFiltersToPostgresClauses:
    """Tests for the full filter conversion pipeline."""

    def test_empty_filters(self):
        result = convert_filters_to_postgres_clauses([])
        assert result == []

    def test_single_include_filter(self):
        filters = [
            TaskMessageEntityFilter(
                content=OptionalTextContentEntity(
                    type=TaskMessageContentType.TEXT,
                    author=MessageAuthor.USER,
                ),
                exclude=False,
            )
        ]
        clauses = convert_filters_to_postgres_clauses(filters)
        assert len(clauses) == 1  # One OR clause wrapping the include

    def test_single_exclude_filter(self):
        filters = [
            TaskMessageEntityFilter(
                content=OptionalDataContentEntity(
                    type=TaskMessageContentType.DATA,
                    author=MessageAuthor.AGENT,
                ),
                exclude=True,
            )
        ]
        clauses = convert_filters_to_postgres_clauses(filters)
        assert len(clauses) == 1  # One negated OR clause

    def test_mixed_include_and_exclude(self):
        filters = [
            TaskMessageEntityFilter(
                content=OptionalTextContentEntity(
                    type=TaskMessageContentType.TEXT,
                    author=MessageAuthor.USER,
                ),
                exclude=False,
            ),
            TaskMessageEntityFilter(
                content=OptionalDataContentEntity(
                    type=TaskMessageContentType.DATA,
                    author=MessageAuthor.AGENT,
                ),
                exclude=True,
            ),
        ]
        clauses = convert_filters_to_postgres_clauses(filters)
        assert len(clauses) == 2  # One include OR + one exclude ~OR

    def test_streaming_status_filter(self):
        filters = [
            TaskMessageEntityFilter(
                streaming_status="IN_PROGRESS",
                exclude=False,
            )
        ]
        clauses = convert_filters_to_postgres_clauses(filters)
        assert len(clauses) == 1

    def test_multiple_include_filters(self):
        filters = [
            TaskMessageEntityFilter(
                content=OptionalTextContentEntity(
                    type=TaskMessageContentType.TEXT,
                    author=MessageAuthor.USER,
                ),
                exclude=False,
            ),
            TaskMessageEntityFilter(
                content=OptionalTextContentEntity(
                    type=TaskMessageContentType.TEXT,
                    author=MessageAuthor.AGENT,
                ),
                exclude=False,
            ),
        ]
        clauses = convert_filters_to_postgres_clauses(filters)
        # Should produce a single OR clause wrapping both includes
        assert len(clauses) == 1
