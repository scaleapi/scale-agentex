"""
Unit tests for TaskStateDualRepository.

These tests verify the phase-switching logic of the dual repository wrapper
without requiring actual database connections.
"""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from domain.entities.states import StateEntity
from domain.repositories.task_state_dual_repository import (
    METRIC_DUAL_READ_LIST_COUNT_MISMATCH,
    METRIC_DUAL_READ_MATCH,
    METRIC_DUAL_READ_MISSING_MONGODB,
    METRIC_DUAL_READ_MISSING_POSTGRES,
    METRIC_DUAL_READ_STATE_MISMATCH,
    TaskStateDualRepository,
)
from utils.ids import orm_id


def create_mock_env_vars(phase: str):
    """Create mock environment variables with the specified phase."""
    mock_env = MagicMock()
    mock_env.TASK_STATE_STORAGE_PHASE = phase
    return mock_env


def create_test_state(task_id: str = None, agent_id: str = None) -> StateEntity:
    """Create a test state entity."""
    return StateEntity(
        id=orm_id(),
        task_id=task_id or orm_id(),
        agent_id=agent_id or orm_id(),
        state={"test": "data", "nested": {"value": 42}},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskStateDualRepositoryMongoDBPhase:
    """Tests for mongodb phase - should only use MongoDB."""

    async def test_create_only_writes_to_mongodb(self):
        """In mongodb phase, create should only write to MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        state = create_test_state()
        mongo_repo.create = AsyncMock(return_value=state)
        postgres_repo.create = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(state)

        mongo_repo.create.assert_called_once_with(state)
        postgres_repo.create.assert_not_called()
        assert result == state

    async def test_get_only_reads_from_mongodb(self):
        """In mongodb phase, get should only read from MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=state)
        postgres_repo.get = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=state.id)

        mongo_repo.get.assert_called_once_with(id=state.id, name=None)
        postgres_repo.get.assert_not_called()
        assert result == state

    async def test_get_by_task_and_agent_only_uses_mongodb(self):
        """In mongodb phase, get_by_task_and_agent should only use MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        state = create_test_state()
        mongo_repo.get_by_task_and_agent = AsyncMock(return_value=state)
        postgres_repo.get_by_task_and_agent = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get_by_task_and_agent(state.task_id, state.agent_id)

        mongo_repo.get_by_task_and_agent.assert_called_once_with(
            state.task_id, state.agent_id
        )
        postgres_repo.get_by_task_and_agent.assert_not_called()
        assert result == state

    async def test_update_only_writes_to_mongodb(self):
        """In mongodb phase, update should only write to MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        state = create_test_state()
        mongo_repo.update = AsyncMock(return_value=state)
        postgres_repo.update = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(state)

        mongo_repo.update.assert_called_once_with(state)
        postgres_repo.update.assert_not_called()
        assert result == state

    async def test_delete_only_deletes_from_mongodb(self):
        """In mongodb phase, delete should only delete from MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_called_once_with(id="test-id", name=None)
        postgres_repo.delete.assert_not_called()

    async def test_list_only_reads_from_mongodb(self):
        """In mongodb phase, list should only read from MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        states = [create_test_state() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=states)
        postgres_repo.list = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.list(limit=10)

        mongo_repo.list.assert_called_once()
        postgres_repo.list.assert_not_called()
        assert result == states


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskStateDualRepositoryDualWritePhase:
    """Tests for dual_write phase - should write to both, read from MongoDB."""

    async def test_create_writes_to_both(self):
        """In dual_write phase, create should write to both MongoDB and PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        state = create_test_state()
        mongo_repo.create = AsyncMock(return_value=state)
        postgres_repo.create = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(state)

        mongo_repo.create.assert_called_once()
        postgres_repo.create.assert_called_once()
        assert result == state

    async def test_create_continues_on_postgres_failure(self):
        """In dual_write phase, create should succeed even if PostgreSQL fails."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        state = create_test_state()
        mongo_repo.create = AsyncMock(return_value=state)
        postgres_repo.create = AsyncMock(side_effect=Exception("PostgreSQL error"))

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(state)

        # Should still return MongoDB result
        assert result == state
        mongo_repo.create.assert_called_once()
        postgres_repo.create.assert_called_once()

    async def test_get_only_reads_from_mongodb(self):
        """In dual_write phase, get should only read from MongoDB."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=state)
        postgres_repo.get = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=state.id)

        mongo_repo.get.assert_called_once()
        postgres_repo.get.assert_not_called()
        assert result == state

    async def test_update_writes_to_both(self):
        """In dual_write phase, update should write to both."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        state = create_test_state()
        mongo_repo.update = AsyncMock(return_value=state)
        postgres_repo.update = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(state)

        mongo_repo.update.assert_called_once()
        postgres_repo.update.assert_called_once()
        assert result == state

    async def test_delete_deletes_from_both(self):
        """In dual_write phase, delete should delete from both."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_called_once()
        postgres_repo.delete.assert_called_once()

    async def test_batch_create_writes_to_both(self):
        """In dual_write phase, batch_create should write to both."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        states = [create_test_state() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock(return_value=states)
        postgres_repo.batch_create = AsyncMock(return_value=states)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(states)

        mongo_repo.batch_create.assert_called_once()
        postgres_repo.batch_create.assert_called_once()
        assert result == states


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskStateDualRepositoryDualReadPhase:
    """Tests for dual_read phase - should write to both, read from both and compare."""

    async def test_get_reads_from_both_and_compares(self):
        """In dual_read phase, get should read from both and log discrepancies."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=state)
        postgres_repo.get = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=state.id)

        mongo_repo.get.assert_called_once()
        postgres_repo.get.assert_called_once()
        # Should return MongoDB result as primary
        assert result == state

    async def test_get_by_task_and_agent_reads_from_both(self):
        """In dual_read phase, get_by_task_and_agent should read from both."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        state = create_test_state()
        mongo_repo.get_by_task_and_agent = AsyncMock(return_value=state)
        postgres_repo.get_by_task_and_agent = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get_by_task_and_agent(state.task_id, state.agent_id)

        mongo_repo.get_by_task_and_agent.assert_called_once()
        postgres_repo.get_by_task_and_agent.assert_called_once()
        assert result == state

    async def test_list_reads_from_both_and_compares_counts(self):
        """In dual_read phase, list should read from both and compare counts."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_states = [create_test_state() for _ in range(3)]
        postgres_states = [create_test_state() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=mongo_states)
        postgres_repo.list = AsyncMock(return_value=postgres_states)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.list()

        mongo_repo.list.assert_called_once()
        postgres_repo.list.assert_called_once()
        # Should return MongoDB results as primary
        assert result == mongo_states


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskStateDualRepositoryPostgresPhase:
    """Tests for postgres phase - should only use PostgreSQL."""

    async def test_create_only_writes_to_postgres(self):
        """In postgres phase, create should only write to PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        state = create_test_state()
        mongo_repo.create = AsyncMock()
        postgres_repo.create = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.create(state)

        mongo_repo.create.assert_not_called()
        postgres_repo.create.assert_called_once_with(state)
        assert result == state

    async def test_get_only_reads_from_postgres(self):
        """In postgres phase, get should only read from PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        state = create_test_state()
        mongo_repo.get = AsyncMock()
        postgres_repo.get = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get(id=state.id)

        mongo_repo.get.assert_not_called()
        postgres_repo.get.assert_called_once()
        assert result == state

    async def test_get_by_task_and_agent_only_uses_postgres(self):
        """In postgres phase, get_by_task_and_agent should only use PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        state = create_test_state()
        mongo_repo.get_by_task_and_agent = AsyncMock()
        postgres_repo.get_by_task_and_agent = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.get_by_task_and_agent(state.task_id, state.agent_id)

        mongo_repo.get_by_task_and_agent.assert_not_called()
        postgres_repo.get_by_task_and_agent.assert_called_once()
        assert result == state

    async def test_update_only_writes_to_postgres(self):
        """In postgres phase, update should only write to PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        state = create_test_state()
        mongo_repo.update = AsyncMock()
        postgres_repo.update = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(state)

        mongo_repo.update.assert_not_called()
        postgres_repo.update.assert_called_once()
        assert result == state

    async def test_delete_only_deletes_from_postgres(self):
        """In postgres phase, delete should only delete from PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock()

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_not_called()
        postgres_repo.delete.assert_called_once()

    async def test_list_only_reads_from_postgres(self):
        """In postgres phase, list should only read from PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        states = [create_test_state() for _ in range(3)]
        mongo_repo.list = AsyncMock()
        postgres_repo.list = AsyncMock(return_value=states)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.list()

        mongo_repo.list.assert_not_called()
        postgres_repo.list.assert_called_once()
        assert result == states

    async def test_batch_create_only_writes_to_postgres(self):
        """In postgres phase, batch_create should only write to PostgreSQL."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        states = [create_test_state() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock()
        postgres_repo.batch_create = AsyncMock(return_value=states)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(states)

        mongo_repo.batch_create.assert_not_called()
        postgres_repo.batch_create.assert_called_once()
        assert result == states


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskStateDualRepositoryErrorHandling:
    """Tests for error handling across phases."""

    async def test_dual_write_update_continues_on_postgres_failure(self):
        """In dual_write phase, update should succeed even if PostgreSQL fails."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        state = create_test_state()
        mongo_repo.update = AsyncMock(return_value=state)
        postgres_repo.update = AsyncMock(side_effect=Exception("PostgreSQL error"))

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.update(state)

        # Should still return MongoDB result
        assert result == state

    async def test_dual_write_delete_continues_on_postgres_failure(self):
        """In dual_write phase, delete should succeed even if PostgreSQL fails."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        mongo_repo.delete = AsyncMock()
        postgres_repo.delete = AsyncMock(side_effect=Exception("PostgreSQL error"))

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        # Should not raise
        await dual_repo.delete(id="test-id")

        mongo_repo.delete.assert_called_once()
        postgres_repo.delete.assert_called_once()

    async def test_dual_write_batch_create_continues_on_postgres_failure(self):
        """In dual_write phase, batch_create should succeed even if PostgreSQL fails."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_write")

        states = [create_test_state() for _ in range(3)]
        mongo_repo.batch_create = AsyncMock(return_value=states)
        postgres_repo.batch_create = AsyncMock(
            side_effect=Exception("PostgreSQL error")
        )

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        result = await dual_repo.batch_create(states)

        # Should still return MongoDB results
        assert result == states


@pytest.mark.asyncio
@pytest.mark.unit
class TestTaskStateDualRepositoryMetrics:
    """Tests for dual_read phase metrics emission."""

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_get_emits_match_metric_when_data_matches(self, mock_statsd):
        """In dual_read phase, matching data should emit match metric."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=state)
        postgres_repo.get = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=state.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MATCH, tags=["operation:get"]
        )

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_get_emits_missing_postgres_metric(self, mock_statsd):
        """In dual_read phase, missing PostgreSQL data should emit mismatch metric."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=state)
        postgres_repo.get = AsyncMock(return_value=None)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=state.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MISSING_POSTGRES, tags=["operation:get"]
        )

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_get_emits_missing_mongodb_metric(self, mock_statsd):
        """In dual_read phase, missing MongoDB data should emit mismatch metric."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=None)
        postgres_repo.get = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=state.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MISSING_MONGODB, tags=["operation:get"]
        )

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_get_emits_state_mismatch_metric(self, mock_statsd):
        """In dual_read phase, differing state content should emit mismatch metric."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_state = create_test_state()
        postgres_state = StateEntity(
            id=mongo_state.id,
            task_id=mongo_state.task_id,
            agent_id=mongo_state.agent_id,
            state={"different": "data"},  # Different state content
            created_at=mongo_state.created_at,
            updated_at=mongo_state.updated_at,
        )
        mongo_repo.get = AsyncMock(return_value=mongo_state)
        postgres_repo.get = AsyncMock(return_value=postgres_state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=mongo_state.id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_STATE_MISMATCH, tags=["operation:get"]
        )

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_get_no_metric_when_both_none(self, mock_statsd):
        """In dual_read phase, both None should not emit any metric."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_repo.get = AsyncMock(return_value=None)
        postgres_repo.get = AsyncMock(return_value=None)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id="nonexistent")

        mock_statsd.increment.assert_not_called()

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_get_by_task_and_agent_emits_match_metric(self, mock_statsd):
        """In dual_read phase, get_by_task_and_agent should emit match metric."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        state = create_test_state()
        mongo_repo.get_by_task_and_agent = AsyncMock(return_value=state)
        postgres_repo.get_by_task_and_agent = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get_by_task_and_agent(state.task_id, state.agent_id)

        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_MATCH, tags=["operation:get_by_task_and_agent"]
        )

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_list_emits_count_mismatch_metric(self, mock_statsd):
        """In dual_read phase, list count mismatch should emit metrics."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_states = [create_test_state() for _ in range(5)]
        postgres_states = [create_test_state() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=mongo_states)
        postgres_repo.list = AsyncMock(return_value=postgres_states)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.list()

        # Should emit both increment and gauge
        mock_statsd.increment.assert_called_once_with(
            METRIC_DUAL_READ_LIST_COUNT_MISMATCH, tags=["operation:list"]
        )
        mock_statsd.gauge.assert_called_once_with(
            "task_state.dual_read.list_count_diff",
            2,  # abs(5 - 3)
            tags=["operation:list"],
        )

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_list_no_metric_when_counts_match(self, mock_statsd):
        """In dual_read phase, matching list counts should not emit count mismatch."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("dual_read")

        mongo_states = [create_test_state() for _ in range(3)]
        postgres_states = [create_test_state() for _ in range(3)]
        mongo_repo.list = AsyncMock(return_value=mongo_states)
        postgres_repo.list = AsyncMock(return_value=postgres_states)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.list()

        mock_statsd.increment.assert_not_called()
        mock_statsd.gauge.assert_not_called()

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_mongodb_phase_no_metrics(self, mock_statsd):
        """In mongodb phase, no metrics should be emitted."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("mongodb")

        state = create_test_state()
        mongo_repo.get = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=state.id)

        mock_statsd.increment.assert_not_called()

    @patch("domain.repositories.task_state_dual_repository.statsd")
    async def test_postgres_phase_no_metrics(self, mock_statsd):
        """In postgres phase, no metrics should be emitted."""
        mongo_repo = MagicMock()
        postgres_repo = MagicMock()
        env_vars = create_mock_env_vars("postgres")

        state = create_test_state()
        postgres_repo.get = AsyncMock(return_value=state)

        dual_repo = TaskStateDualRepository(mongo_repo, postgres_repo, env_vars)
        await dual_repo.get(id=state.id)

        mock_statsd.increment.assert_not_called()
