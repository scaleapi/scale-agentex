"""
PostgreSQL metrics instrumentation following OpenTelemetry semantic conventions.

Metrics are exported via OpenTelemetry SDK to OTLP-compatible backends
(e.g., Grafana Cloud, Datadog Agent, OTel Collector).

Reference: https://opentelemetry.io/docs/specs/semconv/database/
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from datadog import statsd
from sqlalchemy import event
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.pool import AsyncAdaptedQueuePool

from src.utils.logging import make_logger
from src.utils.otel_metrics import get_meter

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram, UpDownCounter
    from sqlalchemy.ext.asyncio import AsyncEngine
    from sqlalchemy.pool import ConnectionPoolEntry

logger = make_logger(__name__)

# Debounce interval for periodic metrics collection (seconds)
_METRICS_DEBOUNCE_INTERVAL = 30

# Slow query threshold in seconds (configurable via environment variable)
_SLOW_QUERY_THRESHOLD = float(os.environ.get("POSTGRES_SLOW_QUERY_THRESHOLD", "0.5"))

# StatsD is only enabled if DD_AGENT_HOST is configured
_STATSD_ENABLED = bool(os.environ.get("DD_AGENT_HOST"))

# Bucket boundaries (seconds) for the connection-acquisition wait histogram.
# The SDK's default boundaries are millisecond-magnitude integers [0, 5, 10, ...]
# that assume a millisecond unit; against a seconds-unit metric almost every
# pool wait (µs–ms normally, up to the ~30s pool_timeout under saturation) falls
# in the first bucket and quantiles are meaningless. These span instant-to-
# timeout so p95/p99 stay usable.
_POOL_WAIT_BUCKET_BOUNDARIES_S = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)


def _format_statsd_tags(attributes: dict) -> list[str]:
    """Convert OTel attributes dict to Datadog StatsD tags list."""
    tag_mapping = {
        "service.name": "service",
        "db.system.name": "db_system",
        "db.client.connection.pool.name": "pool",
        "server.address": "server",
        "db.namespace": "db_name",
        "deployment.environment": "env",
        "db.client.connection.state": "state",
        "db.operation.name": "operation",
        "db.collection.name": "table",
        "error.type": "error_type",
    }
    tags = []
    for key, value in attributes.items():
        tag_name = tag_mapping.get(key, key.replace(".", "_"))
        tags.append(f"{tag_name}:{value}")
    return tags


def _parse_db_url(url: str) -> tuple[str, int, str]:
    """Parse database URL to extract host, port, and database name."""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    db_name = parsed.path.lstrip("/") if parsed.path else "postgres"
    return host, port, db_name


class _PoolWaitInstruments:
    """OTel instruments + attributes for connection-acquisition metrics.

    Held on the pool instance so ``connect()`` can emit without looking back
    through the collector. A ``None`` slot on the pool means OTel is not
    configured and the override degrades to a straight passthrough.
    """

    __slots__ = ("wait_time", "pending_requests", "timeouts", "failures", "attributes")

    def __init__(self, wait_time, pending_requests, timeouts, failures, attributes):
        self.wait_time = wait_time
        self.pending_requests = pending_requests
        self.timeouts = timeouts
        self.failures = failures
        self.attributes = attributes


class InstrumentedAsyncAdaptedQueuePool(AsyncAdaptedQueuePool):
    """Async connection pool that measures connection acquisition.

    Sources the three OTel DB connection-pool metrics that the checkout/checkin
    events in ``PostgresPoolMetrics`` cannot: by the time ``checkout`` fires the
    wait is already over, SQLAlchemy exposes no "started waiting" event, and a
    pool timeout raises before any connection is handed out.

    ``Pool.connect()`` is the single, non-recursive entry point for obtaining a
    connection (``connect() -> _ConnectionFairy._checkout() -> _do_get()``) and
    runs inside the acquiring greenlet, so wall-clock timing around it captures
    the real wait — including time blocked on a saturated pool. Overriding
    ``_do_get`` directly would double-count, because ``QueuePool._do_get``
    recurses on itself on the overflow-retry path.

    Emits (OTel-only; no StatsD dual-emit, these are new series with no Datadog
    consumer yet):
      * ``db.client.connection.wait_time``        — time to obtain a connection
      * ``db.client.connection.pending_requests`` — requests waiting right now
      * ``db.client.connection.timeouts``         — pool acquisition timeouts
      * ``db.client.connection.failures_total``   — non-timeout acquisition
        failures (DB refusing connections, network errors), by ``error.type``

    The pool is constructed inside ``create_async_engine`` before the collector
    has meters, so instruments are attached post-construction; until then, and
    whenever OTel is disabled, ``connect()`` is a plain passthrough.
    """

    # None => passthrough (OTel disabled, or instruments not yet attached).
    _wait_instruments: _PoolWaitInstruments | None = None

    def attach_wait_instruments(self, instruments: _PoolWaitInstruments) -> None:
        self._wait_instruments = instruments

    def recreate(self) -> InstrumentedAsyncAdaptedQueuePool:
        # dispose()/reset recreates the pool object; carry instrumentation
        # forward so metrics don't silently go dark after a pool recreate.
        new_pool = super().recreate()
        new_pool._wait_instruments = self._wait_instruments
        return new_pool

    def connect(self):
        instruments = self._wait_instruments
        if instruments is None:
            return super().connect()

        attributes = instruments.attributes
        instruments.pending_requests.add(1, attributes)
        start = time.monotonic()
        try:
            connection = super().connect()
        except SQLAlchemyTimeoutError:
            instruments.timeouts.add(1, attributes)
            raise
        except Exception as exc:
            # Non-timeout acquisition failure (DB at max_connections, network
            # drop while establishing, auth error). Without this branch the
            # attempt vanishes from metrics: no wait_time sample (nothing was
            # acquired) and no timeout.
            instruments.failures.add(
                1, {**attributes, "error.type": type(exc).__name__}
            )
            raise
        finally:
            instruments.pending_requests.add(-1, attributes)

        # Only reached on success: a timed-out (or otherwise failed) acquisition
        # obtained no connection, so it must not land in the wait_time histogram.
        instruments.wait_time.record(time.monotonic() - start, attributes)
        return connection


class PostgresPoolMetrics:
    """
    Collects and emits PostgreSQL connection pool metrics.

    Registers SQLAlchemy pool event listeners and provides a periodic
    collection method for pool state metrics.

    If OTel is not configured (OTEL_EXPORTER_OTLP_ENDPOINT not set),
    this class becomes a no-op.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        pool_name: str,
        db_url: str,
        environment: str,
        service_name: str = "agentex",
    ):
        self.engine = engine
        self.pool_name = pool_name
        self._last_metrics_time = 0.0

        # Get meter - if None, OTel is not configured
        meter = get_meter("agentex.db.pool")
        self._enabled = meter is not None

        host, port, db_name = _parse_db_url(db_url)

        # Always set base_attributes for StatsD (even if OTel is disabled)
        self.base_attributes = {
            "service.name": service_name,
            "db.system.name": "postgresql",
            "db.client.connection.pool.name": pool_name,
            "server.address": host,
            "server.port": port,
            "db.namespace": db_name,
            "deployment.environment": environment,
        }

        if not self._enabled:
            # Still register pool events for StatsD metrics
            self._register_pool_events()
            return

        self._connection_count: UpDownCounter = meter.create_up_down_counter(
            name="db.client.connection.count",
            description="Current number of connections in the pool",
            unit="{connection}",
        )

        self._connection_max: UpDownCounter = meter.create_up_down_counter(
            name="db.client.connection.max",
            description="Maximum allowed connections",
            unit="{connection}",
        )

        self._connection_overflow: UpDownCounter = meter.create_up_down_counter(
            name="db.client.connection.overflow.current",
            description="Current overflow connections",
            unit="{connection}",
        )

        self._connection_created: Counter = meter.create_counter(
            name="db.client.connection.created_total",
            description="Total connections created",
            unit="{connection}",
        )

        self._connection_invalidated: Counter = meter.create_counter(
            name="db.client.connection.invalidated_total",
            description="Total connections invalidated",
            unit="{connection}",
        )

        self._connection_use_time: Histogram = meter.create_histogram(
            name="db.client.connection.use_time",
            description="Time a connection was checked out",
            unit="s",
        )

        # Connection-acquisition metrics (OTel DB semconv). Sourced from the
        # InstrumentedAsyncAdaptedQueuePool.connect() seam rather than pool
        # events, which can't see the wait, the current waiters, or a timeout.
        self._connection_wait_time: Histogram = meter.create_histogram(
            name="db.client.connection.wait_time",
            description="The time it took to obtain an open connection from the pool",
            unit="s",
            explicit_bucket_boundaries_advisory=_POOL_WAIT_BUCKET_BOUNDARIES_S,
        )

        self._connection_pending_requests: UpDownCounter = meter.create_up_down_counter(
            name="db.client.connection.pending_requests",
            description="The number of current pending requests for an open connection",
            unit="{request}",
        )

        self._connection_timeouts: Counter = meter.create_counter(
            name="db.client.connection.timeouts",
            description=(
                "The number of connection timeouts that have occurred trying to "
                "obtain a connection from the pool"
            ),
            unit="{timeout}",
        )

        # Custom extension (semconv only covers timeouts): acquisitions that
        # failed for any other reason, tagged with error.type.
        self._connection_failures: Counter = meter.create_counter(
            name="db.client.connection.failures_total",
            description=(
                "Connection acquisitions that failed for a reason other than a "
                "pool timeout (DB refusing connections, network errors)"
            ),
            unit="{failure}",
        )

        # Hand the instruments to the pool so its connect() override can emit.
        # Only InstrumentedAsyncAdaptedQueuePool carries the hook; a differently
        # configured engine (e.g. NullPool in tests) is left as a passthrough.
        pool = self.engine.sync_engine.pool
        if isinstance(pool, InstrumentedAsyncAdaptedQueuePool):
            pool.attach_wait_instruments(
                _PoolWaitInstruments(
                    wait_time=self._connection_wait_time,
                    pending_requests=self._connection_pending_requests,
                    timeouts=self._connection_timeouts,
                    failures=self._connection_failures,
                    attributes=self.base_attributes,
                )
            )
        else:
            logger.warning(
                "Pool for %s is %s, not InstrumentedAsyncAdaptedQueuePool; "
                "wait_time/pending_requests/timeouts will not be emitted",
                pool_name,
                type(pool).__name__,
            )

        # Track last reported values for delta calculation
        self._last_idle = 0
        self._last_used = 0
        self._last_overflow = 0
        self._last_max = 0

        self._register_pool_events()

    def _register_pool_events(self):
        """Register SQLAlchemy pool event listeners for timing metrics."""
        sync_pool = self.engine.sync_engine.pool
        base_tags = _format_statsd_tags(self.base_attributes)

        @event.listens_for(sync_pool, "connect")
        def on_connect(
            dbapi_conn,
            connection_record: ConnectionPoolEntry,
        ):
            """Track new connection creation."""
            if self._enabled:
                self._connection_created.add(1, self.base_attributes)
            if _STATSD_ENABLED:
                statsd.increment("db.client.connection.created", tags=base_tags)

        @event.listens_for(sync_pool, "checkout")
        def on_checkout(
            dbapi_conn,
            connection_record: ConnectionPoolEntry,
            connection_proxy,
        ):
            """Track connection checkout - store timestamp for use_time calculation."""
            connection_record.info["_checkout_time"] = time.monotonic()

        @event.listens_for(sync_pool, "checkin")
        def on_checkin(
            dbapi_conn,
            connection_record: ConnectionPoolEntry,
        ):
            """Track connection checkin - calculate use_time."""
            checkout_time = connection_record.info.pop("_checkout_time", None)
            if checkout_time is not None:
                use_time = time.monotonic() - checkout_time
                if self._enabled:
                    self._connection_use_time.record(use_time, self.base_attributes)
                if _STATSD_ENABLED:
                    statsd.histogram(
                        "db.client.connection.use_time", use_time * 1000, tags=base_tags
                    )

        @event.listens_for(sync_pool, "invalidate")
        def on_invalidate(
            dbapi_conn,
            connection_record: ConnectionPoolEntry,
            exception,
        ):
            """Track connection invalidation."""
            error_type = type(exception).__name__ if exception else "unknown"
            attrs = {**self.base_attributes, "error.type": error_type}
            if self._enabled:
                self._connection_invalidated.add(1, attrs)
            if _STATSD_ENABLED:
                error_tags = base_tags + [f"error_type:{error_type}"]
                statsd.increment("db.client.connection.invalidated", tags=error_tags)

    async def collect_pool_metrics(self):
        """
        Collect current pool state metrics with debouncing.

        Only collects metrics if at least _METRICS_DEBOUNCE_INTERVAL seconds
        have passed since the last collection to avoid overhead.
        """
        now = time.monotonic()
        if now - self._last_metrics_time < _METRICS_DEBOUNCE_INTERVAL:
            return

        try:
            self._last_metrics_time = now
            pool = self.engine.sync_engine.pool

            # Connection counts by state
            # Note: pool.overflow() can be negative (relative to max_overflow)
            # Positive overflow means overflow connections are in use
            idle_connections = pool.checkedin()
            used_connections = pool.checkedout()
            raw_overflow = pool.overflow()
            overflow_in_use = max(0, raw_overflow)
            max_connections = pool.size() + pool._max_overflow

            # OTel metrics (if enabled)
            if self._enabled:
                # Record idle connections (delta from last)
                idle_attrs = {
                    **self.base_attributes,
                    "db.client.connection.state": "idle",
                }
                idle_delta = idle_connections - self._last_idle
                if idle_delta != 0:
                    self._connection_count.add(idle_delta, idle_attrs)
                self._last_idle = idle_connections

                # Record used connections (delta from last)
                used_attrs = {
                    **self.base_attributes,
                    "db.client.connection.state": "used",
                }
                used_delta = used_connections - self._last_used
                if used_delta != 0:
                    self._connection_count.add(used_delta, used_attrs)
                self._last_used = used_connections

                # Record overflow connections in use (delta from last)
                overflow_delta = overflow_in_use - self._last_overflow
                if overflow_delta != 0:
                    self._connection_overflow.add(overflow_delta, self.base_attributes)
                self._last_overflow = overflow_in_use

                # Record max connections (delta from last, usually static)
                max_delta = max_connections - self._last_max
                if max_delta != 0:
                    self._connection_max.add(max_delta, self.base_attributes)
                self._last_max = max_connections

            # StatsD metrics (only if Datadog is configured)
            if _STATSD_ENABLED:
                base_tags = _format_statsd_tags(self.base_attributes)

                def _send_statsd_pool_metrics():
                    idle_tags = base_tags + ["state:idle"]
                    used_tags = base_tags + ["state:used"]

                    statsd.gauge(
                        "db.client.connection.count", idle_connections, tags=idle_tags
                    )
                    statsd.gauge(
                        "db.client.connection.count", used_connections, tags=used_tags
                    )
                    statsd.gauge(
                        "db.client.connection.overflow", overflow_in_use, tags=base_tags
                    )
                    statsd.gauge(
                        "db.client.connection.max", max_connections, tags=base_tags
                    )

                await asyncio.to_thread(_send_statsd_pool_metrics)

        except Exception as e:
            logger.error(f"Failed to collect pool metrics for {self.pool_name}: {e}")


class PostgresQueryMetrics:
    """
    Instruments query performance metrics following OTel conventions.

    Registers SQLAlchemy engine events to track query duration, operation
    types, and slow queries.

    If OTel is not configured (OTEL_EXPORTER_OTLP_ENDPOINT not set),
    this class becomes a no-op.
    """

    # Regex patterns to extract operation type
    OPERATION_PATTERNS = [
        (re.compile(r"^\s*SELECT\b", re.IGNORECASE), "SELECT"),
        (re.compile(r"^\s*INSERT\b", re.IGNORECASE), "INSERT"),
        (re.compile(r"^\s*UPDATE\b", re.IGNORECASE), "UPDATE"),
        (re.compile(r"^\s*DELETE\b", re.IGNORECASE), "DELETE"),
        (re.compile(r"^\s*BEGIN\b", re.IGNORECASE), "BEGIN"),
        (re.compile(r"^\s*COMMIT\b", re.IGNORECASE), "COMMIT"),
        (re.compile(r"^\s*ROLLBACK\b", re.IGNORECASE), "ROLLBACK"),
    ]

    # Table extraction pattern
    TABLE_PATTERN = re.compile(
        r"(?:FROM|INTO|UPDATE|JOIN)\s+[\"']?(\w+)[\"']?",
        re.IGNORECASE,
    )

    def __init__(
        self,
        engine: AsyncEngine,
        pool_name: str,
        db_url: str,
        environment: str,
        service_name: str = "agentex",
    ):
        self.engine = engine
        self.pool_name = pool_name

        # Get meter - if None, OTel is not configured
        meter = get_meter("agentex.db.query")
        self._enabled = meter is not None

        host, port, db_name = _parse_db_url(db_url)

        # Always set base_attributes for StatsD (even if OTel is disabled)
        self.base_attributes = {
            "service.name": service_name,
            "db.system.name": "postgresql",
            "db.client.connection.pool.name": pool_name,
            "server.address": host,
            "db.namespace": db_name,
            "deployment.environment": environment,
        }

        # OTel metrics (only if enabled)
        if self._enabled:
            self._operation_duration: Histogram = meter.create_histogram(
                name="db.client.operation.duration",
                description="Database operation duration",
                unit="s",
            )

            self._slow_queries: Counter = meter.create_counter(
                name="db.client.operation.slow_total",
                description="Total slow queries exceeding threshold",
                unit="{query}",
            )

            self._operation_errors: Counter = meter.create_counter(
                name="db.client.operation.errors_total",
                description="Total query errors",
                unit="{error}",
            )

            self._returned_rows: Histogram = meter.create_histogram(
                name="db.client.response.returned_rows",
                description="Number of rows returned by queries",
                unit="{row}",
            )

        self._register_query_events()

    def _extract_operation(self, statement: str) -> str:
        """Extract SQL operation type from statement."""
        for pattern, operation in self.OPERATION_PATTERNS:
            if pattern.match(statement):
                return operation
        return "OTHER"

    def _extract_table(self, statement: str) -> str | None:
        """Extract primary table name from statement."""
        match = self.TABLE_PATTERN.search(statement)
        return match.group(1) if match else None

    def _register_query_events(self):
        """Register SQLAlchemy event listeners for query metrics."""
        sync_engine = self.engine.sync_engine
        base_tags = _format_statsd_tags(self.base_attributes)

        @event.listens_for(sync_engine, "before_cursor_execute")
        def before_execute(
            conn,
            cursor,
            statement: str,
            parameters,
            context: ExecutionContext,
            executemany: bool,
        ):
            """Store query start time in context."""
            context._query_start_time = time.monotonic()

        @event.listens_for(sync_engine, "after_cursor_execute")
        def after_execute(
            conn,
            cursor,
            statement: str,
            parameters,
            context: ExecutionContext,
            executemany: bool,
        ):
            """Calculate and emit query duration metrics."""
            start_time = getattr(context, "_query_start_time", None)
            if start_time is None:
                return

            duration = time.monotonic() - start_time
            operation = self._extract_operation(statement)
            table = self._extract_table(statement)

            attrs = {**self.base_attributes, "db.operation.name": operation}
            if table:
                attrs["db.collection.name"] = table

            # OTel metrics (if enabled)
            if self._enabled:
                # Record operation duration
                self._operation_duration.record(duration, attrs)

                # Track slow queries
                if duration >= _SLOW_QUERY_THRESHOLD:
                    self._slow_queries.add(1, attrs)

                # Record row count for SELECT queries
                if operation == "SELECT" and cursor.rowcount >= 0:
                    self._returned_rows.record(cursor.rowcount, attrs)

            # StatsD metrics (only if Datadog is configured)
            if _STATSD_ENABLED:
                tags = base_tags + [f"operation:{operation}"]
                if table:
                    tags.append(f"table:{table}")

                # Duration in milliseconds for Datadog
                statsd.histogram(
                    "db.client.operation.duration", duration * 1000, tags=tags
                )

                # Track slow queries
                if duration >= _SLOW_QUERY_THRESHOLD:
                    statsd.increment("db.client.operation.slow", tags=tags)

                # Record row count for SELECT queries
                if operation == "SELECT" and cursor.rowcount >= 0:
                    statsd.histogram(
                        "db.client.response.returned_rows", cursor.rowcount, tags=tags
                    )

        @event.listens_for(sync_engine, "handle_error")
        def on_error(exception_context):
            """Track query errors."""
            statement = exception_context.statement or ""
            operation = self._extract_operation(statement)
            original_exception = exception_context.original_exception
            error_type = type(original_exception).__name__

            # Log the error with details for debugging
            # Truncate statement to avoid logging sensitive data
            truncated_stmt = (
                statement[:200] + "..." if len(statement) > 200 else statement
            )
            logger.warning(
                f"Database error on pool {self.pool_name}: "
                f"type={error_type}, operation={operation}, "
                f"message={original_exception}, statement={truncated_stmt}"
            )

            attrs = {
                **self.base_attributes,
                "db.operation.name": operation,
                "error.type": error_type,
            }

            # OTel metrics (if enabled)
            if self._enabled:
                self._operation_errors.add(1, attrs)

            # StatsD metrics (only if Datadog is configured)
            if _STATSD_ENABLED:
                error_tags = base_tags + [
                    f"operation:{operation}",
                    f"error_type:{error_type}",
                ]
                statsd.increment("db.client.operation.errors", tags=error_tags)


class PostgresMetricsCollector:
    """
    Unified collector that manages all PostgreSQL metrics for multiple pools.

    Usage:
        collector = PostgresMetricsCollector()
        collector.register_engine(engine, "main", db_url, environment)
        await collector.start_collection()  # Starts background task
    """

    def __init__(self):
        self._pool_metrics: dict[str, PostgresPoolMetrics] = {}
        self._query_metrics: dict[str, PostgresQueryMetrics] = {}
        self._collection_task: asyncio.Task | None = None

    def register_engine(
        self,
        engine: AsyncEngine,
        pool_name: str,
        db_url: str,
        environment: str,
        service_name: str = "agentex",
    ):
        """Register an engine for metrics collection."""
        self._pool_metrics[pool_name] = PostgresPoolMetrics(
            engine=engine,
            pool_name=pool_name,
            db_url=db_url,
            environment=environment,
            service_name=service_name,
        )
        self._query_metrics[pool_name] = PostgresQueryMetrics(
            engine=engine,
            pool_name=pool_name,
            db_url=db_url,
            environment=environment,
            service_name=service_name,
        )
        logger.info(f"Registered PostgreSQL metrics for pool: {pool_name}")

    async def collect_all_metrics(self):
        """Collect all pool metrics once."""
        tasks = []

        for metrics in self._pool_metrics.values():
            tasks.append(metrics.collect_pool_metrics())

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _collection_loop(self):
        """Background loop that collects metrics periodically."""
        while True:
            try:
                await self.collect_all_metrics()
            except Exception as e:
                logger.error(f"Error in metrics collection loop: {e}")
            await asyncio.sleep(_METRICS_DEBOUNCE_INTERVAL)

    async def start_collection(self):
        """Start the background metrics collection task."""
        if self._collection_task is None:
            self._collection_task = asyncio.create_task(self._collection_loop())
            logger.info("Started PostgreSQL metrics collection background task")

    async def stop_collection(self):
        """Stop the background metrics collection task."""
        if self._collection_task is not None:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
            self._collection_task = None
            logger.info("Stopped PostgreSQL metrics collection background task")
