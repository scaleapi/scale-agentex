"""
Unit tests for TaskMessageDualRepository.

These tests verify the phase-switching logic of the dual repository wrapper
without requiring actual database connections.
"""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from domain.entities.task_messages import (
    MessageAuthor,
    TaskMessageContentType,
    TaskMessageEntity,
    TextContentEntity,
)
from domain.repositories.task_message_dual_repository import (
    METRIC_DUAL_READ_CONTENT_MISMATCH,
    METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
    METRIC_DUAL_READ_MATCH,
    METRIC_DUAL_READ_MISSING_MONGODB,
    METRIC_DUAL_READ_MISSING_POSTGRES,
    TaskMessageDualRepository,
)
from utils.ids import orm_id


def create_mock_env_vars(phase: str):
    """Create mock environment variables with the specified phase."""
    mock_env = MagicMock()
    mock_env.TASK_MESSAGE_STORAGE_PHASE = phase
    return mock_env


def create_test_message(task_id: str = None) -> TaskMessageEntity:
    """Create a test message entity."""
    return TaskMessageEntity(
        id=orm_id(),
        task_id=task_id or orm_id(),
        content=TextContentEntity(
            type=TaskMessageContentType.TEXT,
            author=MessageAuthor.USER,
            content="Hello, world!",
        ),
        streaming_status=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryMongoDBPhase:
    """Tests for mongodb phase - should only use MongoDB."""

    async def test_create_only_writes_to_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msg = create_test_message()
        mongo_repo.create = AsyncMock(return_value=msg)
        postgres_repo.create = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(msg)

        mongo_repo.create.assert_called_once_with(msg)
        postgres_repo.create.assert_not_called()
        assert result == msg

    async def test_get_only_reads_from_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=msg)
        postgres_repo.get = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=msg.id)

        mongo_repo.get.assert_called_once_with(id=msg.id, name=None)
        postgres_repo.get.assert_not_called()
        assert result == msg

    async def test_update_only_writes_to_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msg = create_test_message()
        mongo_repo.update = AsyncMock(return_value=msg)
        postgres_repo.update = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(msg)

        mongo_repo.update.assert_called_once_with(msg)
        postgres_repo.update.assert_not_called()
        assert result == msg

    async def test_delete_only_deletes_from_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_called_once_with(id="test-id", name=None)
        postgres_repo.delete.assert_not_called()

    async def test_batch_create_only_writes_to_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock(return_value=msgs)
        postgres_repo.batch_create = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(msgs)

        mongo_repo.batch_create.assert_called_once()
        postgres_repo.batch_create.assert_not_called()
        assert result == msgs

    async def test_delete_by_field_only_uses_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        mongo_repo.delete_by_field = AsyncMock(return_value=5)
        postgres_repo.delete_by_field = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.delete_by_field("task_id", "test-task")

        mongo_repo.delete_by_field.assert_called_once_with("task_id", "test-task")
        postgres_repo.delete_by_field.assert_not_called()
        assert result == 5

    async def test_find_by_field_only_reads_from_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field = AsyncMock(return_value=msgs)
        postgres_repo.find_by_field = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.find_by_field("task_id", "test-task", limit=10)

        mongo_repo.find_by_field.assert_called_once()
        postgres_repo.find_by_field.assert_not_called()
        assert result == msgs

    async def test_find_by_field_with_cursor_only_reads_from_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field_with_cursor = AsyncMock(return_value=msgs)
        postgres_repo.find_by_field_with_cursor = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.find_by_field_with_cursor(
            "task_id", "test-task", limit=10, before_id="cursor-id"
        )

        mongo_repo.find_by_field_with_cursor.assert_called_once()
        postgres_repo.find_by_field_with_cursor.assert_not_called()
        assert result == msgs

    async def test_list_only_reads_from_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=msgs)
        postgres_repo.list = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.list(limit=10)

        mongo_repo.list.assert_called_once()
        postgres_repo.list.assert_not_called()
        assert result == msgs


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryDualWritePhase:
    """Tests for dual_write phase - should write to both, read from MongoDB."""

    async def test_create_writes_to_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msg = create_test_message()
        mongo_repo.create = AsyncMock(return_value=msg)
        postgres_repo.create = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(msg)

        mongo_repo.create.assert_called_once()
        postgres_repo.create.assert_called_once()
        assert result == msg

    async def test_create_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msg = create_test_message()
        mongo_repo.create = AsyncMock(return_value=msg)
        postgres_repo.create = AsyncMock(side_effect=Exception("PostgreSQL error"))

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(msg)

        assert result == msg
        mongo_repo.create.assert_called_once()
        postgres_repo.create.assert_called_once()

    async def test_get_only_reads_from_mongodb(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=msg)
        postgres_repo.get = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=msg.id)

        mongo_repo.get.assert_called_once()
        postgres_repo.get.assert_not_called()
        assert result == msg

    async def test_update_writes_to_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msg = create_test_message()
        mongo_repo.update = AsyncMock(return_value=msg)
        postgres_repo.update = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(msg)

        mongo_repo.update.assert_called_once()
        postgres_repo.update.assert_called_once()
        assert result == msg

    async def test_delete_deletes_from_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_called_once()
        postgres_repo.delete.assert_called_once()

    async def test_batch_create_writes_to_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock(return_value=msgs)
        postgres_repo.batch_create = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(msgs)

        mongo_repo.batch_create.assert_called_once()
        postgres_repo.batch_create.assert_called_once()
        assert result == msgs

    async def test_delete_by_field_deletes_from_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.delete_by_field = AsyncMock(return_value=3)
        postgres_repo.delete_by_field = AsyncMock(return_value=3)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.delete_by_field("task_id", "test-task")

        mongo_repo.delete_by_field.assert_called_once()
        postgres_repo.delete_by_field.assert_called_once()
        assert result == 3

    async def test_batch_delete_deletes_from_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.batch_delete = AsyncMock()
        postgres_repo.batch_delete = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.batch_delete(ids=["id1", "id2"])

        mongo_repo.batch_delete.assert_called_once()
        postgres_repo.batch_delete.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryDualReadPhase:
    """Tests for dual_read phase - should write to both, read from both and compare."""

    async def test_get_reads_from_both_and_compares(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=msg)
        postgres_repo.get = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=msg.id)

        mongo_repo.get.assert_called_once()
        postgres_repo.get.assert_called_once()
        assert result == msg

    async def test_find_by_field_reads_from_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field = AsyncMock(return_value=msgs)
        postgres_repo.find_by_field = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.find_by_field("task_id", "test-task", limit=10)

        mongo_repo.find_by_field.assert_called_once()
        postgres_repo.find_by_field.assert_called_once()
        assert result == msgs

    async def test_find_by_field_with_cursor_reads_from_both(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field_with_cursor = AsyncMock(return_value=msgs)
        postgres_repo.find_by_field_with_cursor = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.find_by_field_with_cursor(
            "task_id", "test-task", limit=10, before_id="cursor-id"
        )

        mongo_repo.find_by_field_with_cursor.assert_called_once()
        postgres_repo.find_by_field_with_cursor.assert_called_once()
        assert result == msgs

    async def test_list_reads_from_both_and_compares_counts(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_msgs = [create_test_message() for _ in range(3)]
        postgres_msgs = [create_test_message() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=mongo_msgs)
        postgres_repo.list = AsyncMock(return_value=postgres_msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.list()

        mongo_repo.list.assert_called_once()
        postgres_repo.list.assert_called_once()
        assert result == mongo_msgs


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryPostgresPhase:
    """Tests for postgres phase - should only use PostgreSQL."""

    async def test_create_only_writes_to_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msg = create_test_message()
        mongo_repo.create = AsyncMock()
        postgres_repo.create = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(msg)

        mongo_repo.create.assert_not_called()
        postgres_repo.create.assert_called_once_with(msg)
        assert result == msg

    async def test_get_only_reads_from_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msg = create_test_message()
        mongo_repo.get = AsyncMock()
        postgres_repo.get = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=msg.id)

        mongo_repo.get.assert_not_called()
        postgres_repo.get.assert_called_once()
        assert result == msg

    async def test_update_only_writes_to_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msg = create_test_message()
        mongo_repo.update = AsyncMock()
        postgres_repo.update = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(msg)

        mongo_repo.update.assert_not_called()
        postgres_repo.update.assert_called_once()
        assert result == msg

    async def test_delete_only_deletes_from_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock()

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_not_called()
        postgres_repo.delete.assert_called_once()

    async def test_batch_create_only_writes_to_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock()
        postgres_repo.batch_create = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(msgs)

        mongo_repo.batch_create.assert_not_called()
        postgres_repo.batch_create.assert_called_once()
        assert result == msgs

    async def test_delete_by_field_only_uses_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        mongo_repo.delete_by_field = AsyncMock()
        postgres_repo.delete_by_field = AsyncMock(return_value=5)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.delete_by_field("task_id", "test-task")

        mongo_repo.delete_by_field.assert_not_called()
        postgres_repo.delete_by_field.assert_called_once()
        assert result == 5

    async def test_find_by_field_only_reads_from_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field = AsyncMock()
        postgres_repo.find_by_field = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.find_by_field("task_id", "test-task", limit=10)

        mongo_repo.find_by_field.assert_not_called()
        postgres_repo.find_by_field.assert_called_once()
        assert result == msgs

    async def test_find_by_field_with_cursor_only_reads_from_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field_with_cursor = AsyncMock()
        postgres_repo.find_by_field_with_cursor = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.find_by_field_with_cursor(
            "task_id", "test-task", limit=10, before_id="cursor-id"
        )

        mongo_repo.find_by_field_with_cursor.assert_not_called()
        postgres_repo.find_by_field_with_cursor.assert_called_once()
        assert result == msgs

    async def test_list_only_reads_from_postgres(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.list = AsyncMock()
        postgres_repo.list = AsyncMock(return_value=msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.list()

        mongo_repo.list.assert_not_called()
        postgres_repo.list.assert_called_once()
        assert result == msgs


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryErrorHandling:
    """Tests for error handling across phases."""

    async def test_dual_write_update_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msg = create_test_message()
        mongo_repo.update = AsyncMock(return_value=msg)
        postgres_repo.update = AsyncMock(side_effect=Exception("PostgreSQL error"))

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(msg)

        assert result == msg

    async def test_dual_write_delete_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock(side_effect=Exception("PostgreSQL error"))

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_called_once()
        postgres_repo.delete.assert_called_once()

    async def test_dual_write_batch_create_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msgs = [create_test_message() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock(return_value=msgs)
        postgres_repo.batch_create = AsyncMock(
            side_effect=Exception("PostgreSQL error")
        )

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(msgs)

        assert result == msgs

    async def test_dual_write_delete_by_field_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.delete_by_field = AsyncMock(return_value=3)
        postgres_repo.delete_by_field = AsyncMock(
            side_effect=Exception("PostgreSQL error")
        )

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.delete_by_field("task_id", "test-task")

        assert result == 3

    async def test_dual_write_batch_delete_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.batch_delete = AsyncMock()
        postgres_repo.batch_delete = AsyncMock(
            side_effect=Exception("PostgreSQL error")
        )

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.batch_delete(ids=["id1", "id2"])

        mongo_repo.batch_delete.assert_called_once()

    async def test_dual_write_batch_update_continues_on_postgres_failure(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        msgs = [create_test_message() for _ in range(2)]
        mongo_repo.batch_update = AsyncMock(return_value=msgs)
        postgres_repo.batch_update = AsyncMock(
            side_effect=Exception("PostgreSQL error")
        )

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_update(msgs)

        assert result == msgs


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryMetrics:
    """Tests for dual_read phase metrics emission."""

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_get_emits_match_metric_when_data_matches(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=msg)
        postgres_repo.get = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=msg.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MATCH, tags=["operation:get"]
        )

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_get_emits_missing_postgres_metric(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=msg)
        postgres_repo.get = AsyncMock(return_value=None)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=msg.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MISSING_POSTGRES, tags=["operation:get"]
        )

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_get_emits_missing_mongodb_metric(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=None)
        postgres_repo.get = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=msg.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MISSING_MONGODB, tags=["operation:get"]
        )

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_get_emits_content_mismatch_metric(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_msg = create_test_message()
        postgres_msg = TaskMessageEntity(
            id=mongo_msg.id,
            task_id=mongo_msg.task_id,
            content=TextContentEntity(
                type=TaskMessageContentType.TEXT,
                author=MessageAuthor.AGENT,
                content="Different content!",
            ),
            created_at=mongo_msg.created_at,
            updated_at=mongo_msg.updated_at,
        )
        mongo_repo.get = AsyncMock(return_value=mongo_msg)
        postgres_repo.get = AsyncMock(return_value=postgres_msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=mongo_msg.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_CONTENT_MISMATCH, tags=["operation:get"]
        )

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_get_no_metric_when_both_none(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_repo.get = AsyncMock(return_value=None)
        postgres_repo.get = AsyncMock(return_value=None)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id="nonexistent")

        mock_statsd.increment.assert_not_called()

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_find_by_field_emits_count_mismatch_metric(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_msgs = [create_test_message() for _ in range(5)]
        postgres_msgs = [create_test_message() for _ in range(3)]
        mongo_repo.find_by_field = AsyncMock(return_value=mongo_msgs)
        postgres_repo.find_by_field = AsyncMock(return_value=postgres_msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.find_by_field("task_id", "test-task", limit=10)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
            tags=["operation:find_by_field"],
        )
        mock_statsd.gauge.assert_called_once_with(
            "task_message.dual_read.list_count_diff",
            2,
            tags=["operation:find_by_field"],
        )

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_list_emits_count_mismatch_metric(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_msgs = [create_test_message() for _ in range(5)]
        postgres_msgs = [create_test_message() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=mongo_msgs)
        postgres_repo.list = AsyncMock(return_value=postgres_msgs)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.list()

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
            tags=["operation:list"],
        )

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_mongodb_phase_no_metrics(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msg = create_test_message()
        mongo_repo.get = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=msg.id)

        mock_statsd.increment.assert_not_called()

    @patch("domain.repositories.task_message_dual_repository.statsd")
    async def test_postgres_phase_no_metrics(self, mock_statsd):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        msg = create_test_message()
        postgres_repo.get = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=msg.id)

        mock_statsd.increment.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskMessageDualRepositoryStorageOverride:
    """Tests for storage phase override via query parameter."""

    async def test_override_forces_postgres_phase(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")  # default is mongodb

        msg = create_test_message()
        mongo_repo.create = AsyncMock()
        postgres_repo.create = AsyncMock(return_value=msg)

        # Override to postgres
        dual_repo = TaskMessageDualRepository(
            mongo_repo, postgres_repo, env_vars, storage_phase_override="postgres"
        )
        result = await dual_repo.create(msg)

        mongo_repo.create.assert_not_called()
        postgres_repo.create.assert_called_once()
        assert result == msg

    async def test_override_forces_dual_write_phase(self):
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        msg = create_test_message()
        mongo_repo.create = AsyncMock(return_value=msg)
        postgres_repo.create = AsyncMock(return_value=msg)

        dual_repo = TaskMessageDualRepository(
            mongo_repo, postgres_repo, env_vars, storage_phase_override="dual_write"
        )
        await dual_repo.create(msg)

        mongo_repo.create.assert_called_once()
        postgres_repo.create.assert_called_once()
