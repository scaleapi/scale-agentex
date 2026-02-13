#!/usr/bin/env python3
"""
API-level benchmark for task state storage.

Tests the full HTTP stack including connection pooling, serialization, and middleware.

Prerequisites:
    Start the API server: make dev
    The server should be running on http://localhost:5003

Usage:
    uv run python scripts/benchmarks/benchmark_api.py --duration 10 --concurrency 1,10,25

    # Test with specific storage backend (requires setting TASK_STATE_STORAGE_PHASE env var on server)
    uv run python scripts/benchmarks/benchmark_api.py --label mongodb --output results/api_mongodb.json
    uv run python scripts/benchmarks/benchmark_api.py --label postgres --output results/api_postgres.json
"""

import argparse
import asyncio
import random
import string
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from scripts.benchmarks.metrics import (
    BenchmarkResults,
    ScenarioMetrics,
    print_scenario_summary,
)
from scripts.benchmarks.scenarios import BenchmarkConfig, Operation

# Default API base URL
DEFAULT_API_URL = "http://localhost:5003"


def generate_state_data(size_bytes: int) -> dict[str, Any]:
    """Generate state data of approximately the target size."""
    base = {"key": "value", "metadata": {"created_by": "api_benchmark"}}
    base_size = len(str(base).encode("utf-8"))
    padding_needed = max(0, size_bytes - base_size)
    padding = "".join(
        random.choices(string.ascii_letters + string.digits, k=padding_needed)
    )
    return {
        "key": "value",
        "metadata": {"created_by": "api_benchmark", "version": 1},
        "data": padding,
    }


class APIBenchmarkData:
    """Track created states for API benchmark."""

    def __init__(self, state_size: int):
        self.state_size = state_size
        self.created_states: list[
            dict
        ] = []  # {"id": str, "task_id": str, "agent_id": str}

    def get_unique_ids(self) -> tuple[str, str]:
        """Generate unique task_id and agent_id."""
        return str(uuid.uuid4()), str(uuid.uuid4())

    def add_state(self, state_id: str, task_id: str, agent_id: str) -> None:
        self.created_states.append(
            {
                "id": state_id,
                "task_id": task_id,
                "agent_id": agent_id,
            }
        )

    def random_state(self) -> dict | None:
        if not self.created_states:
            return None
        return random.choice(self.created_states)

    def remove_state(self, state_id: str) -> None:
        self.created_states = [s for s in self.created_states if s["id"] != state_id]


# Operation weights matching production patterns
OPERATION_WEIGHTS = {
    Operation.GET_BY_TASK_AGENT: 40,
    Operation.UPDATE: 25,
    Operation.CREATE: 15,
    Operation.LIST_BY_TASK: 10,
    Operation.GET_BY_ID: 5,
    Operation.LIST_BY_AGENT: 3,
    Operation.DELETE: 2,
}


def weighted_operation_choice() -> Operation:
    """Choose an operation based on weights."""
    ops = list(OPERATION_WEIGHTS.keys())
    weights = list(OPERATION_WEIGHTS.values())
    return random.choices(ops, weights=weights, k=1)[0]


async def run_operation(
    client: httpx.AsyncClient,
    operation: Operation,
    data: APIBenchmarkData,
    storage_backend: str | None = None,
) -> tuple[float, bool]:
    """Run a single API operation and return (latency_ms, had_error)."""
    # Add storage_backend query param if specified
    backend_params = {"storage_backend": storage_backend} if storage_backend else {}

    try:
        start = time.perf_counter()

        if operation == Operation.CREATE:
            task_id, agent_id = data.get_unique_ids()
            response = await client.post(
                "/states",
                params=backend_params,
                json={
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "state": generate_state_data(data.state_size),
                },
            )
            if response.status_code == 200:
                result = response.json()
                data.add_state(result["id"], task_id, agent_id)

        elif operation == Operation.GET_BY_ID:
            state = data.random_state()
            if not state:
                return 0.0, True
            response = await client.get(f"/states/{state['id']}", params=backend_params)

        elif operation == Operation.GET_BY_TASK_AGENT:
            state = data.random_state()
            if state:
                # Query for existing state
                response = await client.get(
                    "/states",
                    params={
                        "task_id": state["task_id"],
                        "agent_id": state["agent_id"],
                        "limit": 1,
                        **backend_params,
                    },
                )
            else:
                # Query for non-existent (still valid test)
                response = await client.get(
                    "/states",
                    params={
                        "task_id": str(uuid.uuid4()),
                        "agent_id": str(uuid.uuid4()),
                        "limit": 1,
                        **backend_params,
                    },
                )

        elif operation == Operation.UPDATE:
            state = data.random_state()
            if not state:
                return 0.0, True
            response = await client.put(
                f"/states/{state['id']}",
                params=backend_params,
                json={
                    "task_id": state["task_id"],
                    "agent_id": state["agent_id"],
                    "state": generate_state_data(data.state_size),
                },
            )

        elif operation == Operation.DELETE:
            state = data.random_state()
            if not state:
                return 0.0, True
            response = await client.delete(
                f"/states/{state['id']}", params=backend_params
            )
            if response.status_code == 200:
                data.remove_state(state["id"])
                # Create a replacement to maintain pool
                task_id, agent_id = data.get_unique_ids()
                await client.post(
                    "/states",
                    params=backend_params,
                    json={
                        "task_id": task_id,
                        "agent_id": agent_id,
                        "state": generate_state_data(data.state_size),
                    },
                )

        elif operation == Operation.LIST_BY_TASK:
            state = data.random_state()
            task_id = state["task_id"] if state else str(uuid.uuid4())
            response = await client.get(
                "/states", params={"task_id": task_id, "limit": 50, **backend_params}
            )

        elif operation == Operation.LIST_BY_AGENT:
            state = data.random_state()
            agent_id = state["agent_id"] if state else str(uuid.uuid4())
            response = await client.get(
                "/states", params={"agent_id": agent_id, "limit": 50, **backend_params}
            )

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Check for errors
        if response.status_code >= 400:
            return elapsed_ms, True

        return elapsed_ms, False

    except Exception as e:
        print(f"Error in {operation}: {e}")
        return 0.0, True


async def run_api_scenario(
    api_url: str,
    concurrency: int,
    state_size: int,
    duration_seconds: int,
    warmup_ops: int,
    label: str,
    storage_backend: str | None = None,
) -> ScenarioMetrics:
    """Run an API benchmark scenario."""
    backend_info = f" (storage_backend={storage_backend})" if storage_backend else ""
    print(
        f"\nRunning API scenario: concurrency={concurrency}, state_size={state_size}{backend_info}"
    )

    metrics = ScenarioMetrics(
        storage_type=label,
        concurrency=concurrency,
        state_size=state_size,
        duration_seconds=duration_seconds,
    )

    # Use connection pooling with limits matching concurrency
    limits = httpx.Limits(
        max_keepalive_connections=concurrency * 2,
        max_connections=concurrency * 2,
        keepalive_expiry=30,
    )
    timeout = httpx.Timeout(30.0, connect=10.0)

    async with httpx.AsyncClient(
        base_url=api_url,
        limits=limits,
        timeout=timeout,
    ) as client:
        # Verify API is accessible
        try:
            params = {"limit": 1}
            if storage_backend:
                params["storage_backend"] = storage_backend
            response = await client.get("/states", params=params)
            if response.status_code != 200:
                print(f"Warning: API returned {response.status_code}")
        except Exception as e:
            print(f"Error: Cannot connect to API at {api_url}: {e}")
            return metrics

        data = APIBenchmarkData(state_size=state_size)

        # Pre-populate states
        print("Pre-populating test data...")
        for _ in range(50):
            await run_operation(client, Operation.CREATE, data, storage_backend)

        # Warmup
        print(f"Warming up ({warmup_ops} operations)...")
        for _ in range(warmup_ops):
            op = weighted_operation_choice()
            await run_operation(client, op, data, storage_backend)

        # Main benchmark
        print(
            f"Running benchmark for {duration_seconds} seconds with {concurrency} workers..."
        )
        stop_event = asyncio.Event()
        metrics.start_time = time.time()

        async def worker():
            while not stop_event.is_set():
                op = weighted_operation_choice()
                latency_ms, had_error = await run_operation(
                    client, op, data, storage_backend
                )
                metrics.get_or_create_operation(op.value).record(latency_ms, had_error)

        # Create worker tasks
        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

        # Wait for duration
        await asyncio.sleep(duration_seconds)
        stop_event.set()

        # Cancel workers
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        metrics.end_time = time.time()

    print_scenario_summary(metrics)
    return metrics


async def main_async(args):
    """Async main function."""
    config = BenchmarkConfig(
        concurrency_levels=[int(x) for x in args.concurrency.split(",")],
        state_sizes=[int(x) for x in args.state_sizes.split(",")],
        duration_seconds=args.duration,
        warmup_ops=args.warmup,
    )

    # Determine storage backend: explicit arg > infer from label > None (use server default)
    storage_backend = args.storage_backend
    if not storage_backend and args.label in ("mongodb", "postgres"):
        storage_backend = args.label

    output_path = (
        Path(args.output)
        if args.output
        else Path(f"scripts/benchmarks/results/api_{args.label}.json")
    )

    print("API Benchmark Configuration:")
    print(f"  API URL: {args.api_url}")
    print(f"  Label: {args.label}")
    print(f"  Storage backend: {storage_backend or '(server default)'}")
    print(f"  Concurrency levels: {config.concurrency_levels}")
    print(f"  State sizes: {config.state_sizes}")
    print(f"  Duration per scenario: {config.duration_seconds}s")
    print(f"  Warmup operations: {config.warmup_ops}")
    print(f"  Output: {output_path}")

    results = BenchmarkResults(
        storage_type=args.label,
        metadata={
            "api_url": args.api_url,
            "storage_backend": storage_backend,
            "concurrency_levels": config.concurrency_levels,
            "state_sizes": config.state_sizes,
            "duration_seconds": config.duration_seconds,
            "warmup_ops": config.warmup_ops,
            "timestamp": datetime.now().isoformat(),
        },
    )

    for state_size in config.state_sizes:
        for concurrency in config.concurrency_levels:
            scenario = await run_api_scenario(
                api_url=args.api_url,
                concurrency=concurrency,
                state_size=state_size,
                duration_seconds=config.duration_seconds,
                warmup_ops=config.warmup_ops,
                label=args.label,
                storage_backend=storage_backend,
            )
            results.add_scenario(scenario)

    results.save(output_path)

    print(f"\n{'=' * 60}")
    print(f"Benchmark complete! Results saved to {output_path}")
    print(f"Total scenarios: {len(results.scenarios)}")


def main():
    parser = argparse.ArgumentParser(
        description="API-level benchmark for task state storage"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=DEFAULT_API_URL,
        help=f"API base URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="api",
        help="Label for this benchmark run (e.g., 'mongodb', 'postgres')",
    )
    parser.add_argument(
        "--concurrency",
        type=str,
        default="1,10,25",
        help="Comma-separated concurrency levels (default: 1,10,25)",
    )
    parser.add_argument(
        "--state-sizes",
        type=str,
        default="100,1000",
        help="Comma-separated state sizes in bytes (default: 100,1000)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Duration per scenario in seconds (default: 10)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=50,
        help="Number of warmup operations (default: 50)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: results/api_<label>.json)",
    )
    parser.add_argument(
        "--storage-backend",
        type=str,
        default=None,
        choices=["mongodb", "postgres", "dual_write", "dual_read"],
        help="Override storage backend via query param (default: inferred from --label if 'mongodb' or 'postgres')",
    )

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
