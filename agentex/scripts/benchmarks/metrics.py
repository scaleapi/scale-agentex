"""
Metrics collection and reporting for benchmark results.
"""

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""

    operation: str
    total_ops: int = 0
    total_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def p50(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.quantiles(self.latencies_ms, n=100)[49]

    @property
    def p95(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.quantiles(self.latencies_ms, n=100)[94]

    @property
    def p99(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.quantiles(self.latencies_ms, n=100)[98]

    @property
    def mean(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)

    @property
    def stdev(self) -> float:
        if len(self.latencies_ms) < 2:
            return 0.0
        return statistics.stdev(self.latencies_ms)

    @property
    def min_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return min(self.latencies_ms)

    @property
    def max_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return max(self.latencies_ms)

    def record(self, latency_ms: float, error: bool = False) -> None:
        """Record a single operation result."""
        self.total_ops += 1
        if error:
            self.total_errors += 1
        else:
            self.latencies_ms.append(latency_ms)

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "total_ops": self.total_ops,
            "total_errors": self.total_errors,
            "successful_ops": len(self.latencies_ms),
            "error_rate": self.total_errors / self.total_ops
            if self.total_ops > 0
            else 0,
            "p50_ms": round(self.p50, 3),
            "p95_ms": round(self.p95, 3),
            "p99_ms": round(self.p99, 3),
            "mean_ms": round(self.mean, 3),
            "stdev_ms": round(self.stdev, 3),
            "min_ms": round(self.min_latency, 3),
            "max_ms": round(self.max_latency, 3),
        }


@dataclass
class ScenarioMetrics:
    """Metrics for a complete benchmark scenario."""

    storage_type: str
    concurrency: int
    state_size: int
    duration_seconds: float
    operations: dict[str, OperationMetrics] = field(default_factory=dict)
    start_time: float = 0.0
    end_time: float = 0.0

    def get_or_create_operation(self, operation: str) -> OperationMetrics:
        """Get or create metrics for an operation."""
        if operation not in self.operations:
            self.operations[operation] = OperationMetrics(operation=operation)
        return self.operations[operation]

    @property
    def actual_duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return self.duration_seconds

    @property
    def total_ops(self) -> int:
        return sum(op.total_ops for op in self.operations.values())

    @property
    def total_errors(self) -> int:
        return sum(op.total_errors for op in self.operations.values())

    @property
    def ops_per_second(self) -> float:
        if self.actual_duration == 0:
            return 0.0
        return self.total_ops / self.actual_duration

    def to_dict(self) -> dict:
        return {
            "storage_type": self.storage_type,
            "concurrency": self.concurrency,
            "state_size": self.state_size,
            "duration_seconds": round(self.actual_duration, 2),
            "total_ops": self.total_ops,
            "total_errors": self.total_errors,
            "ops_per_second": round(self.ops_per_second, 2),
            "operations": {name: op.to_dict() for name, op in self.operations.items()},
        }


@dataclass
class BenchmarkResults:
    """Complete benchmark results."""

    storage_type: str
    scenarios: list[ScenarioMetrics] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_scenario(self, scenario: ScenarioMetrics) -> None:
        self.scenarios.append(scenario)

    def to_dict(self) -> dict:
        return {
            "storage_type": self.storage_type,
            "metadata": self.metadata,
            "scenarios": [s.to_dict() for s in self.scenarios],
        }

    def save(self, path: Path) -> None:
        """Save results to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"Results saved to {path}")

    @classmethod
    def load(cls, path: Path) -> "BenchmarkResults":
        """Load results from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            storage_type=data["storage_type"],
            metadata=data.get("metadata", {}),
            scenarios=[],  # Scenarios are loaded as dicts, not reconstructed
        )


class Timer:
    """Context manager for timing operations."""

    def __init__(self):
        self.start_time: float = 0
        self.end_time: float = 0

    def __enter__(self) -> "Timer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.end_time = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


def print_scenario_summary(scenario: ScenarioMetrics) -> None:
    """Print a summary of scenario results."""
    print(f"\n{'=' * 60}")
    print(
        f"Storage: {scenario.storage_type} | Concurrency: {scenario.concurrency} | State Size: {scenario.state_size} bytes"
    )
    print(
        f"Duration: {scenario.actual_duration:.2f}s | Total Ops: {scenario.total_ops} | Throughput: {scenario.ops_per_second:.2f} ops/sec"
    )
    print(f"{'=' * 60}")
    print(
        f"{'Operation':<25} {'Count':>8} {'Errors':>8} {'P50 ms':>10} {'P95 ms':>10} {'P99 ms':>10}"
    )
    print("-" * 71)
    for name, op in sorted(scenario.operations.items()):
        print(
            f"{name:<25} {op.total_ops:>8} {op.total_errors:>8} {op.p50:>10.2f} {op.p95:>10.2f} {op.p99:>10.2f}"
        )
