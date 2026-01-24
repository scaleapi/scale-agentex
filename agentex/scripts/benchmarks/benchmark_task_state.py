#!/usr/bin/env python3
"""
Local benchmark runner for comparing MongoDB vs PostgreSQL task state storage.

Prerequisites:
    Install dev dependencies: make install-dev
    Start services: make dev

Usage:
    uv run python scripts/benchmarks/benchmark_task_state.py --storage mongodb --output results/mongodb.json
    uv run python scripts/benchmarks/benchmark_task_state.py --storage postgres --output results/postgres.json
"""

import argparse
import asyncio
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.benchmarks.metrics import (
    BenchmarkResults,
    ScenarioMetrics,
    Timer,
    print_scenario_summary,
)
from scripts.benchmarks.scenarios import (
    BenchmarkConfig,
    Operation,
    TestData,
    weighted_operation_choice,
)


def setup_environment():
    """Ensure environment is set for local development."""
    if not os.environ.get("ENVIRONMENT"):
        os.environ["ENVIRONMENT"] = "development"


class MongoDBBenchmark:
    """Benchmark runner for MongoDB storage."""

    def __init__(self, mongodb_uri: str | None = None):
        self.repository = None
        self.db = None
        self._mongodb_uri = mongodb_uri

    def setup(self):
        """Initialize MongoDB connection and repository."""
        from pymongo import MongoClient
        from src.config.environment_variables import EnvironmentVariables
        from src.domain.repositories.task_state_repository import TaskStateRepository

        env_vars = EnvironmentVariables.refresh(force_refresh=True)
        mongodb_uri = (
            self._mongodb_uri or env_vars.MONGODB_URI or "mongodb://localhost:27017"
        )
        mongodb_database = env_vars.MONGODB_DATABASE_NAME or "agentex"

        client = MongoClient(mongodb_uri)
        self.db = client[mongodb_database]
        self.repository = TaskStateRepository(db=self.db)

    def teardown(self):
        """Clean up MongoDB connection."""
        if self.db is not None:
            self.db.client.close()

    def run_operation(
        self, operation: Operation, test_data: TestData
    ) -> tuple[float, bool]:
        """Run a single operation and return (latency_ms, had_error)."""
        from src.adapters.crud_store.exceptions import ItemDoesNotExist
        from src.domain.entities.states import StateEntity

        try:
            with Timer() as timer:
                if operation == Operation.CREATE:
                    # Use unique pair to avoid duplicate key errors
                    task_id, agent_id = test_data.get_unique_task_agent_pair()
                    entity = StateEntity(
                        task_id=task_id,
                        agent_id=agent_id,
                        state=test_data.state_data.copy(),
                    )
                    # MongoDB repository create is async, run it in event loop
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(self.repository.create(entity))
                        test_data.add_created_state(result.id, task_id, agent_id)
                    finally:
                        loop.close()

                elif operation == Operation.GET_BY_ID:
                    state_id = test_data.random_created_state_id()
                    if state_id:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(self.repository.get(id=state_id))
                        finally:
                            loop.close()
                    else:
                        return 0.0, True  # No states to get

                elif operation == Operation.GET_BY_TASK_AGENT:
                    task_id = test_data.random_task_id()
                    agent_id = test_data.random_agent_id()
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            self.repository.get_by_task_and_agent(
                                task_id=task_id, agent_id=agent_id
                            )
                        )
                    finally:
                        loop.close()

                elif operation == Operation.UPDATE:
                    state_id = test_data.random_created_state_id()
                    if state_id:
                        loop = asyncio.new_event_loop()
                        try:
                            existing = loop.run_until_complete(
                                self.repository.get(id=state_id)
                            )
                            existing.state = test_data.state_data.copy()
                            existing.state["updated_at"] = datetime.now().isoformat()
                            loop.run_until_complete(self.repository.update(existing))
                        finally:
                            loop.close()
                    else:
                        return 0.0, True

                elif operation == Operation.DELETE:
                    state_id = test_data.random_created_state_id()
                    if state_id:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(self.repository.delete(id=state_id))
                            test_data.remove_created_state(state_id)
                        finally:
                            loop.close()
                    else:
                        return 0.0, True

                elif operation == Operation.LIST_BY_TASK:
                    task_id = test_data.random_task_id()
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            self.repository.list(filters={"task_id": task_id}, limit=50)
                        )
                    finally:
                        loop.close()

                elif operation == Operation.LIST_BY_AGENT:
                    agent_id = test_data.random_agent_id()
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            self.repository.list(
                                filters={"agent_id": agent_id}, limit=50
                            )
                        )
                    finally:
                        loop.close()

            return timer.elapsed_ms, False

        except ItemDoesNotExist:
            return 0.0, True
        except Exception as e:
            print(f"Error in {operation}: {e}")
            return 0.0, True


class PostgresBenchmark:
    """Benchmark runner for PostgreSQL storage using asyncio."""

    def __init__(self, database_url: str | None = None):
        self.repository = None
        self.rw_session_maker = None
        self.ro_session_maker = None
        self._database_url = database_url

    async def setup(self):
        """Initialize PostgreSQL connection and repository."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from src.config.environment_variables import EnvironmentVariables
        from src.domain.repositories.task_state_postgres_repository import (
            TaskStatePostgresRepository,
        )

        env_vars = EnvironmentVariables.refresh(force_refresh=True)
        database_url = self._database_url or env_vars.DATABASE_URL

        if not database_url:
            database_url = (
                "postgresql+asyncpg://postgres:postgres@localhost:5432/agentex"
            )

        # Convert sync URL to async if needed
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

        engine = create_async_engine(
            database_url,
            pool_size=50,
            max_overflow=50,
            pool_pre_ping=True,
        )

        self.rw_session_maker = async_sessionmaker(engine, expire_on_commit=False)
        self.ro_session_maker = self.rw_session_maker  # Use same for benchmark

        self.repository = TaskStatePostgresRepository(
            async_read_write_session_maker=self.rw_session_maker,
            async_read_only_session_maker=self.ro_session_maker,
        )

    async def teardown(self):
        """Clean up PostgreSQL connections."""
        # Session makers don't need explicit cleanup in SQLAlchemy 2.0
        pass

    async def run_operation(
        self, operation: Operation, test_data: TestData
    ) -> tuple[float, bool]:
        """Run a single operation and return (latency_ms, had_error)."""
        from src.adapters.crud_store.exceptions import ItemDoesNotExist
        from src.domain.entities.states import StateEntity
        from src.utils.ids import orm_id

        try:
            start = time.perf_counter()

            if operation == Operation.CREATE:
                # Use unique pair to avoid duplicate key errors
                task_id, agent_id = test_data.get_unique_task_agent_pair()
                entity = StateEntity(
                    id=orm_id(),
                    task_id=task_id,
                    agent_id=agent_id,
                    state=test_data.state_data.copy(),
                )
                result = await self.repository.create(entity)
                test_data.add_created_state(result.id, task_id, agent_id)

            elif operation == Operation.GET_BY_ID:
                state_id = test_data.random_created_state_id()
                if state_id:
                    await self.repository.get(id=state_id)
                else:
                    return 0.0, True

            elif operation == Operation.GET_BY_TASK_AGENT:
                task_id = test_data.random_task_id()
                agent_id = test_data.random_agent_id()
                await self.repository.get_by_task_and_agent(
                    task_id=task_id, agent_id=agent_id
                )

            elif operation == Operation.UPDATE:
                state_id = test_data.random_created_state_id()
                if state_id:
                    existing = await self.repository.get(id=state_id)
                    existing.state = test_data.state_data.copy()
                    existing.state["updated_at"] = datetime.now().isoformat()
                    await self.repository.update(existing)
                else:
                    return 0.0, True

            elif operation == Operation.DELETE:
                state_id = test_data.random_created_state_id()
                if state_id:
                    await self.repository.delete(id=state_id)
                    test_data.remove_created_state(state_id)
                else:
                    return 0.0, True

            elif operation == Operation.LIST_BY_TASK:
                task_id = test_data.random_task_id()
                await self.repository.list(filters={"task_id": task_id}, limit=50)

            elif operation == Operation.LIST_BY_AGENT:
                agent_id = test_data.random_agent_id()
                await self.repository.list(filters={"agent_id": agent_id}, limit=50)

            elapsed_ms = (time.perf_counter() - start) * 1000
            return elapsed_ms, False

        except ItemDoesNotExist:
            return 0.0, True
        except Exception as e:
            print(f"Error in {operation}: {e}")
            return 0.0, True


def run_mongodb_scenario(
    config: BenchmarkConfig,
    concurrency: int,
    state_size: int,
    mongodb_uri: str | None = None,
) -> ScenarioMetrics:
    """Run a benchmark scenario for MongoDB using threading."""
    print(
        f"\nRunning MongoDB scenario: concurrency={concurrency}, state_size={state_size}"
    )

    benchmark = MongoDBBenchmark(mongodb_uri=mongodb_uri)
    benchmark.setup()

    test_data = TestData.generate(num_tasks=100, num_agents=10, state_size=state_size)
    metrics = ScenarioMetrics(
        storage_type="mongodb",
        concurrency=concurrency,
        state_size=state_size,
        duration_seconds=config.duration_seconds,
    )

    # Pre-populate some states for read/update/delete operations
    print("Pre-populating test data...")
    for _ in range(50):
        benchmark.run_operation(Operation.CREATE, test_data)

    # Warmup
    print(f"Warming up ({config.warmup_ops} operations)...")
    for _ in range(config.warmup_ops):
        op = weighted_operation_choice()
        benchmark.run_operation(op, test_data)

    # Main benchmark
    print(f"Running benchmark for {config.duration_seconds} seconds...")
    stop_flag = False
    metrics.start_time = time.time()
    end_time = metrics.start_time + config.duration_seconds

    def worker():
        while not stop_flag and time.time() < end_time:
            op = weighted_operation_choice()
            latency_ms, had_error = benchmark.run_operation(op, test_data)
            metrics.get_or_create_operation(op.value).record(latency_ms, had_error)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(concurrency)]
        try:
            # Wait for duration
            time.sleep(config.duration_seconds)
            stop_flag = True
            for f in futures:
                f.result(timeout=5)
        except KeyboardInterrupt:
            stop_flag = True

    metrics.end_time = time.time()
    benchmark.teardown()

    print_scenario_summary(metrics)
    return metrics


async def run_postgres_scenario(
    config: BenchmarkConfig,
    concurrency: int,
    state_size: int,
    database_url: str | None = None,
) -> ScenarioMetrics:
    """Run a benchmark scenario for PostgreSQL using asyncio."""
    print(
        f"\nRunning PostgreSQL scenario: concurrency={concurrency}, state_size={state_size}"
    )

    benchmark = PostgresBenchmark(database_url=database_url)
    await benchmark.setup()

    test_data = TestData.generate(num_tasks=100, num_agents=10, state_size=state_size)
    metrics = ScenarioMetrics(
        storage_type="postgres",
        concurrency=concurrency,
        state_size=state_size,
        duration_seconds=config.duration_seconds,
    )

    # Pre-populate some states for read/update/delete operations
    print("Pre-populating test data...")
    for _ in range(50):
        await benchmark.run_operation(Operation.CREATE, test_data)

    # Warmup
    print(f"Warming up ({config.warmup_ops} operations)...")
    for _ in range(config.warmup_ops):
        op = weighted_operation_choice()
        await benchmark.run_operation(op, test_data)

    # Main benchmark
    print(f"Running benchmark for {config.duration_seconds} seconds...")
    stop_event = asyncio.Event()
    metrics.start_time = time.time()

    async def worker():
        while not stop_event.is_set():
            op = weighted_operation_choice()
            latency_ms, had_error = await benchmark.run_operation(op, test_data)
            metrics.get_or_create_operation(op.value).record(latency_ms, had_error)

    # Create worker tasks
    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

    # Wait for duration
    await asyncio.sleep(config.duration_seconds)
    stop_event.set()

    # Cancel workers and wait for them to finish
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    metrics.end_time = time.time()
    await benchmark.teardown()

    print_scenario_summary(metrics)
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark MongoDB vs PostgreSQL task state storage"
    )
    parser.add_argument(
        "--storage",
        choices=["mongodb", "postgres"],
        required=True,
        help="Storage backend to benchmark",
    )
    parser.add_argument(
        "--concurrency",
        type=str,
        default="1,10,25,50",
        help="Comma-separated concurrency levels (default: 1,10,25,50)",
    )
    parser.add_argument(
        "--state-sizes",
        type=str,
        default="100,1000,10000",
        help="Comma-separated state sizes in bytes (default: 100,1000,10000)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration per scenario in seconds (default: 30)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=100,
        help="Number of warmup operations (default: 100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: results/<storage>.json)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick benchmark with reduced parameters",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="PostgreSQL connection URL (default: from DATABASE_URL env or postgresql+asyncpg://postgres:postgres@localhost:5432/agentex)",
    )
    parser.add_argument(
        "--mongodb-uri",
        type=str,
        default=None,
        help="MongoDB connection URI (default: from MONGODB_URI env or mongodb://localhost:27017)",
    )

    args = parser.parse_args()

    setup_environment()

    # Parse config
    if args.quick:
        config = BenchmarkConfig.quick()
    else:
        config = BenchmarkConfig(
            concurrency_levels=[int(x) for x in args.concurrency.split(",")],
            state_sizes=[int(x) for x in args.state_sizes.split(",")],
            duration_seconds=args.duration,
            warmup_ops=args.warmup,
        )

    # Determine output path
    output_path = (
        Path(args.output)
        if args.output
        else Path(f"scripts/benchmarks/results/{args.storage}.json")
    )

    print("Benchmark Configuration:")
    print(f"  Storage: {args.storage}")
    print(f"  Concurrency levels: {config.concurrency_levels}")
    print(f"  State sizes: {config.state_sizes}")
    print(f"  Duration per scenario: {config.duration_seconds}s")
    print(f"  Warmup operations: {config.warmup_ops}")
    print(f"  Output: {output_path}")

    results = BenchmarkResults(
        storage_type=args.storage,
        metadata={
            "concurrency_levels": config.concurrency_levels,
            "state_sizes": config.state_sizes,
            "duration_seconds": config.duration_seconds,
            "warmup_ops": config.warmup_ops,
            "timestamp": datetime.now().isoformat(),
        },
    )

    # Run scenarios
    for state_size in config.state_sizes:
        for concurrency in config.concurrency_levels:
            if args.storage == "mongodb":
                scenario = run_mongodb_scenario(
                    config, concurrency, state_size, mongodb_uri=args.mongodb_uri
                )
            else:
                scenario = asyncio.run(
                    run_postgres_scenario(
                        config, concurrency, state_size, database_url=args.database_url
                    )
                )

            results.add_scenario(scenario)

    # Save results
    results.save(output_path)

    print(f"\n{'=' * 60}")
    print(f"Benchmark complete! Results saved to {output_path}")
    print(f"Total scenarios: {len(results.scenarios)}")


if __name__ == "__main__":
    main()
