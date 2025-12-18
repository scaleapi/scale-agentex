"""
Unit tests for PostgreSQL performance logging utility.

Tests the PostgresPerformanceLogger class for tracking query performance,
emitting StatsD metrics, and logging query details.
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from utils.postgres_perf_logging import (
    PostgresPerformanceLogger,
    QueryMetrics,
    QueryType,
    create_postgres_perf_logger,
)


@pytest.fixture
def mock_env_vars():
    """Create mock environment variables with perf logging enabled."""
    mock = MagicMock()
    mock.POSTGRES_PERF_LOGGING_ENABLED = True
    mock.POSTGRES_SLOW_QUERY_THRESHOLD_MS = 100.0
    mock.POSTGRES_PERF_LOGGING_SAMPLE_RATE = 1.0
    mock.ENVIRONMENT = "test"
    return mock


@pytest.fixture
def mock_env_vars_disabled():
    """Create mock environment variables with perf logging disabled."""
    mock = MagicMock()
    mock.POSTGRES_PERF_LOGGING_ENABLED = False
    mock.POSTGRES_SLOW_QUERY_THRESHOLD_MS = 100.0
    mock.POSTGRES_PERF_LOGGING_SAMPLE_RATE = 1.0
    mock.ENVIRONMENT = "test"
    return mock


@pytest.fixture
def perf_logger(mock_env_vars):
    """Create performance logger with mock env vars."""
    return PostgresPerformanceLogger(mock_env_vars)


class TestQueryType:
    """Tests for QueryType enum."""

    @pytest.mark.unit
    def test_query_types_exist(self):
        """Test that all expected query types are defined."""
        assert QueryType.SELECT == "SELECT"
        assert QueryType.INSERT == "INSERT"
        assert QueryType.UPDATE == "UPDATE"
        assert QueryType.DELETE == "DELETE"
        assert QueryType.BATCH_INSERT == "BATCH_INSERT"
        assert QueryType.BATCH_UPDATE == "BATCH_UPDATE"
        assert QueryType.BATCH_DELETE == "BATCH_DELETE"
        assert QueryType.BATCH_SELECT == "BATCH_SELECT"


class TestQueryMetrics:
    """Tests for QueryMetrics dataclass."""

    @pytest.mark.unit
    def test_query_metrics_creation(self):
        """Test that QueryMetrics can be created with all fields."""
        metrics = QueryMetrics(
            query_type=QueryType.SELECT,
            table_name="agents",
            execution_time_ms=50.5,
            is_slow_query=False,
            slow_query_threshold_ms=100.0,
            request_id="test-123",
            extra_tags={"custom": "tag"},
        )

        assert metrics.query_type == QueryType.SELECT
        assert metrics.table_name == "agents"
        assert metrics.execution_time_ms == 50.5
        assert metrics.is_slow_query is False
        assert metrics.slow_query_threshold_ms == 100.0
        assert metrics.request_id == "test-123"
        assert metrics.extra_tags == {"custom": "tag"}


class TestPostgresPerformanceLogger:
    """Tests for PostgresPerformanceLogger class."""

    @pytest.mark.unit
    def test_logger_initialization(self, mock_env_vars):
        """Test that logger initializes with correct settings."""
        logger = PostgresPerformanceLogger(mock_env_vars)

        assert logger._enabled is True
        assert logger._slow_threshold_ms == 100.0
        assert logger._sample_rate == 1.0
        assert logger._environment == "test"

    @pytest.mark.unit
    def test_create_postgres_perf_logger_factory(self, mock_env_vars):
        """Test the factory function creates a logger."""
        logger = create_postgres_perf_logger(mock_env_vars)

        assert isinstance(logger, PostgresPerformanceLogger)
        assert logger._enabled is True

    @pytest.mark.unit
    def test_build_statsd_tags(self, perf_logger):
        """Test that StatsD tags are built correctly."""
        tags = perf_logger._build_statsd_tags(
            query_type=QueryType.SELECT,
            table_name="agents",
            is_slow=False,
            extra_tags={"custom": "value"},
        )

        assert "env:test" in tags
        assert "query_type:SELECT" in tags
        assert "table:agents" in tags
        assert "slow:false" in tags
        assert "custom:value" in tags

    @pytest.mark.unit
    def test_build_statsd_tags_slow_query(self, perf_logger):
        """Test that slow query tag is set correctly."""
        tags = perf_logger._build_statsd_tags(
            query_type=QueryType.SELECT,
            table_name="agents",
            is_slow=True,
        )

        assert "slow:true" in tags

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_track_query_emits_metrics(self, perf_logger):
        """Test that track_query emits StatsD metrics."""
        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            async with perf_logger.track_query(QueryType.SELECT, "agents"):
                pass

            # Verify histogram was called for duration
            mock_statsd.histogram.assert_called_once()
            call_args = mock_statsd.histogram.call_args
            assert call_args[0][0] == "postgres.query.duration"
            assert "table:agents" in call_args[1]["tags"]
            assert "query_type:SELECT" in call_args[1]["tags"]

            # Verify increment was called for query count
            mock_statsd.increment.assert_called_once()
            count_call = mock_statsd.increment.call_args
            assert count_call[0][0] == "postgres.query.count"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_slow_query_detection(self, mock_env_vars):
        """Test that slow queries are detected and logged at WARNING level."""
        # Use a very low threshold to ensure we trigger slow query
        mock_env_vars.POSTGRES_SLOW_QUERY_THRESHOLD_MS = 1.0
        perf_logger = PostgresPerformanceLogger(mock_env_vars)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            with patch("utils.postgres_perf_logging.logger") as mock_logger:
                async with perf_logger.track_query(QueryType.SELECT, "agents"):
                    # Simulate a slow query
                    time.sleep(0.01)  # 10ms

                # Verify slow query counter was incremented
                # increment is called twice: once for count, once for slow
                assert mock_statsd.increment.call_count == 2

                # Verify warning was logged
                mock_logger.warning.assert_called_once()
                warning_msg = mock_logger.warning.call_args[0][0]
                assert "Slow query detected" in warning_msg

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_logging_disabled_globally(self, mock_env_vars_disabled):
        """Test that no metrics are emitted when logging is globally disabled."""
        perf_logger = PostgresPerformanceLogger(mock_env_vars_disabled)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            async with perf_logger.track_query(QueryType.SELECT, "agents"):
                pass

            # Verify no metrics were emitted
            mock_statsd.histogram.assert_not_called()
            mock_statsd.increment.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_per_query_override_enable(self, mock_env_vars_disabled):
        """Test per-query override to enable logging."""
        perf_logger = PostgresPerformanceLogger(mock_env_vars_disabled)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            # Override to enable for this specific query
            async with perf_logger.track_query(
                QueryType.SELECT, "agents", enable_logging=True
            ):
                pass

            # Verify metrics were emitted despite global disable
            mock_statsd.histogram.assert_called_once()
            mock_statsd.increment.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_per_query_override_disable(self, mock_env_vars):
        """Test per-query override to disable logging."""
        perf_logger = PostgresPerformanceLogger(mock_env_vars)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            # Override to disable for this specific query
            async with perf_logger.track_query(
                QueryType.SELECT, "agents", enable_logging=False
            ):
                pass

            # Verify no metrics were emitted
            mock_statsd.histogram.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sample_rate_zero(self, mock_env_vars):
        """Test that 0% sampling emits nothing."""
        mock_env_vars.POSTGRES_PERF_LOGGING_SAMPLE_RATE = 0.0
        perf_logger = PostgresPerformanceLogger(mock_env_vars)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            async with perf_logger.track_query(QueryType.SELECT, "agents"):
                pass

            # Verify no metrics emitted due to 0% sample rate
            mock_statsd.histogram.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sample_rate_full(self, mock_env_vars):
        """Test that 100% sampling always emits."""
        mock_env_vars.POSTGRES_PERF_LOGGING_SAMPLE_RATE = 1.0
        perf_logger = PostgresPerformanceLogger(mock_env_vars)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            # Run multiple times to verify consistent behavior
            for _ in range(5):
                async with perf_logger.track_query(QueryType.SELECT, "agents"):
                    pass

            # All 5 should have emitted metrics
            assert mock_statsd.histogram.call_count == 5

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extra_tags_included(self, perf_logger):
        """Test that extra tags are included in metrics."""
        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            async with perf_logger.track_query(
                QueryType.INSERT,
                "tasks",
                extra_tags={"operation_id": "abc123"},
            ):
                pass

            call_args = mock_statsd.histogram.call_args
            tags = call_args[1]["tags"]
            assert "operation_id:abc123" in tags

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_request_id_from_context(self, perf_logger):
        """Test that request_id is captured from context."""
        with patch("utils.postgres_perf_logging.ctx_var_request_id") as mock_ctx:
            mock_ctx.get.return_value = "request-12345"

            with patch("utils.postgres_perf_logging.logger") as mock_logger:
                async with perf_logger.track_query(QueryType.SELECT, "agents"):
                    pass

                # Verify logger was called with request_id in extra
                call_args = mock_logger.debug.call_args
                extra = call_args[1]["extra"]
                assert extra["request_id"] == "request-12345"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_timing_accuracy(self, mock_env_vars):
        """Test that timing is reasonably accurate."""
        mock_env_vars.POSTGRES_SLOW_QUERY_THRESHOLD_MS = 1000.0  # High threshold
        perf_logger = PostgresPerformanceLogger(mock_env_vars)

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            async with perf_logger.track_query(QueryType.SELECT, "agents"):
                time.sleep(0.05)  # 50ms

            call_args = mock_statsd.histogram.call_args
            duration = call_args[0][1]  # Second positional arg is the value

            # Should be approximately 50ms (allow some variance)
            assert 40 < duration < 100  # Allow variance for test environment

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_different_query_types(self, perf_logger):
        """Test that different query types are correctly tagged."""
        query_types = [
            QueryType.SELECT,
            QueryType.INSERT,
            QueryType.UPDATE,
            QueryType.DELETE,
            QueryType.BATCH_SELECT,
            QueryType.BATCH_INSERT,
            QueryType.BATCH_UPDATE,
            QueryType.BATCH_DELETE,
        ]

        with patch("utils.postgres_perf_logging.statsd") as mock_statsd:
            for qt in query_types:
                async with perf_logger.track_query(qt, "test_table"):
                    pass

            assert mock_statsd.histogram.call_count == len(query_types)

            # Verify each query type was tagged correctly
            for i, qt in enumerate(query_types):
                call_args = mock_statsd.histogram.call_args_list[i]
                tags = call_args[1]["tags"]
                assert f"query_type:{qt.value}" in tags
