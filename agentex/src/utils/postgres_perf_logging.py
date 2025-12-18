"""
PostgreSQL Performance Logging Utility

Provides timing context manager and metrics for database operations.
Integrates with Datadog StatsD and JSON logging for observability.
"""

from __future__ import annotations

import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from datadog import statsd

from src.utils.logging import ctx_var_request_id, make_logger

if TYPE_CHECKING:
    from src.config.environment_variables import EnvironmentVariables

logger = make_logger(__name__)


class QueryType(StrEnum):
    """Database query operation types"""

    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    BATCH_INSERT = "BATCH_INSERT"
    BATCH_UPDATE = "BATCH_UPDATE"
    BATCH_DELETE = "BATCH_DELETE"
    BATCH_SELECT = "BATCH_SELECT"


@dataclass
class QueryMetrics:
    """Container for query performance metrics"""

    query_type: QueryType
    table_name: str
    execution_time_ms: float
    is_slow_query: bool
    slow_query_threshold_ms: float
    request_id: str | None = None
    extra_tags: dict[str, Any] | None = None


class PostgresPerformanceLogger:
    """
    Performance logger for PostgreSQL operations.

    Handles timing, logging, and StatsD metrics emission.
    Designed to be used as an async context manager.
    """

    # StatsD metric names
    METRIC_QUERY_DURATION = "postgres.query.duration"
    METRIC_SLOW_QUERY_COUNT = "postgres.query.slow"
    METRIC_QUERY_COUNT = "postgres.query.count"

    def __init__(
        self,
        environment_variables: EnvironmentVariables,
    ):
        self._enabled = environment_variables.POSTGRES_PERF_LOGGING_ENABLED
        self._slow_threshold_ms = environment_variables.POSTGRES_SLOW_QUERY_THRESHOLD_MS
        self._sample_rate = environment_variables.POSTGRES_PERF_LOGGING_SAMPLE_RATE
        self._environment = environment_variables.ENVIRONMENT

    def _should_sample(self) -> bool:
        """Determine if this query should be sampled based on sample rate"""
        if self._sample_rate >= 1.0:
            return True
        return random.random() < self._sample_rate

    def _build_statsd_tags(
        self,
        query_type: QueryType,
        table_name: str,
        is_slow: bool,
        extra_tags: dict[str, Any] | None = None,
    ) -> list[str]:
        """Build tags list for StatsD metrics"""
        tags = [
            f"env:{self._environment}",
            f"query_type:{query_type.value}",
            f"table:{table_name}",
            f"slow:{str(is_slow).lower()}",
        ]
        if extra_tags:
            for key, value in extra_tags.items():
                tags.append(f"{key}:{value}")
        return tags

    def _emit_statsd_metrics(self, metrics: QueryMetrics) -> None:
        """Emit StatsD metrics for the query"""
        tags = self._build_statsd_tags(
            query_type=metrics.query_type,
            table_name=metrics.table_name,
            is_slow=metrics.is_slow_query,
            extra_tags=metrics.extra_tags,
        )

        # Emit histogram for query duration (supports percentiles in Datadog)
        statsd.histogram(
            self.METRIC_QUERY_DURATION,
            metrics.execution_time_ms,
            tags=tags,
        )

        # Emit counter for query count
        statsd.increment(
            self.METRIC_QUERY_COUNT,
            tags=tags,
        )

        # Emit counter for slow queries
        if metrics.is_slow_query:
            statsd.increment(
                self.METRIC_SLOW_QUERY_COUNT,
                tags=tags,
            )

    def _log_query_performance(self, metrics: QueryMetrics) -> None:
        """Log query performance in JSON format (Datadog compatible)"""
        log_data = {
            "event": "postgres_query_performance",
            "query_type": metrics.query_type.value,
            "table": metrics.table_name,
            "duration_ms": round(metrics.execution_time_ms, 3),
            "is_slow_query": metrics.is_slow_query,
            "slow_threshold_ms": metrics.slow_query_threshold_ms,
        }

        if metrics.request_id:
            log_data["request_id"] = metrics.request_id

        if metrics.extra_tags:
            log_data["extra"] = metrics.extra_tags

        if metrics.is_slow_query:
            logger.warning(
                f"Slow query detected: {metrics.query_type.value} on {metrics.table_name} "
                f"took {metrics.execution_time_ms:.2f}ms (threshold: {metrics.slow_query_threshold_ms}ms)",
                extra=log_data,
            )
        else:
            logger.debug(
                f"Query: {metrics.query_type.value} on {metrics.table_name} "
                f"took {metrics.execution_time_ms:.2f}ms",
                extra=log_data,
            )

    @asynccontextmanager
    async def track_query(
        self,
        query_type: QueryType,
        table_name: str,
        *,
        enable_logging: bool | None = None,
        extra_tags: dict[str, Any] | None = None,
    ):
        """
        Async context manager for tracking query performance.

        Args:
            query_type: The type of database operation (SELECT, INSERT, etc.)
            table_name: Name of the table being queried
            enable_logging: Override global setting for this specific query.
                          None = use global setting, True = force enable, False = force disable
            extra_tags: Additional tags to include in metrics

        Usage:
            async with perf_logger.track_query(QueryType.SELECT, "agents"):
                result = await session.execute(query)
        """
        # Determine if logging is enabled for this query
        is_enabled = enable_logging if enable_logging is not None else self._enabled

        # Early exit if disabled or not sampled
        if not is_enabled or not self._should_sample():
            yield
            return

        # Get request ID from context if available
        request_id = ctx_var_request_id.get(None)

        # Start timing
        start_time = time.perf_counter()

        try:
            yield
        finally:
            # Calculate execution time
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000

            # Determine if this is a slow query
            is_slow = execution_time_ms > self._slow_threshold_ms

            # Create metrics object
            metrics = QueryMetrics(
                query_type=query_type,
                table_name=table_name,
                execution_time_ms=execution_time_ms,
                is_slow_query=is_slow,
                slow_query_threshold_ms=self._slow_threshold_ms,
                request_id=request_id,
                extra_tags=extra_tags,
            )

            # Emit StatsD metrics
            self._emit_statsd_metrics(metrics)

            # Log the performance data
            self._log_query_performance(metrics)


def create_postgres_perf_logger(
    environment_variables: EnvironmentVariables,
) -> PostgresPerformanceLogger:
    """Create a PostgresPerformanceLogger instance"""
    return PostgresPerformanceLogger(environment_variables)
