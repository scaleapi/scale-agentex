"""
Test scenario definitions for task state benchmarks.
"""

import random
import string
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Operation(str, Enum):
    """Benchmark operations."""

    CREATE = "create"
    GET_BY_ID = "get_by_id"
    GET_BY_TASK_AGENT = "get_by_task_agent"
    UPDATE = "update"
    DELETE = "delete"
    LIST_BY_TASK = "list_by_task"
    LIST_BY_AGENT = "list_by_agent"


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""

    concurrency_levels: list[int]
    state_sizes: list[int]  # in bytes
    duration_seconds: int
    warmup_ops: int

    @classmethod
    def default(cls) -> "BenchmarkConfig":
        return cls(
            concurrency_levels=[1, 10, 25, 50],
            state_sizes=[100, 1000, 10000],
            duration_seconds=30,
            warmup_ops=100,
        )

    @classmethod
    def quick(cls) -> "BenchmarkConfig":
        """Quick config for testing the benchmark itself."""
        return cls(
            concurrency_levels=[1, 5],
            state_sizes=[100, 1000],
            duration_seconds=5,
            warmup_ops=10,
        )


def generate_state_data(size_bytes: int) -> dict[str, Any]:
    """Generate state data of approximately the target size."""
    # Base overhead for the dict structure
    base = {"key": "value", "metadata": {}}

    # Calculate padding needed
    base_size = len(str(base).encode("utf-8"))
    padding_needed = max(0, size_bytes - base_size)

    # Generate random string padding
    padding = "".join(
        random.choices(string.ascii_letters + string.digits, k=padding_needed)
    )

    return {
        "key": "value",
        "metadata": {
            "created_by": "benchmark",
            "version": 1,
        },
        "data": padding,
    }


def generate_task_id() -> str:
    """Generate a unique task ID."""
    return str(uuid.uuid4())


def generate_agent_id() -> str:
    """Generate a unique agent ID."""
    return str(uuid.uuid4())


@dataclass
class CreatedState:
    """Represents a created state entry."""

    state_id: str
    task_id: str
    agent_id: str


class TestData:
    """Pre-generated test data for benchmark scenarios.

    Tracks unique (task_id, agent_id) combinations since MongoDB enforces
    uniqueness on this compound key.
    """

    def __init__(
        self,
        task_ids: list[str],
        agent_ids: list[str],
        state_data: dict[str, Any],
    ):
        self.task_ids = task_ids
        self.agent_ids = agent_ids
        self.state_data = state_data
        # Track created states with their task_id/agent_id for proper lookups
        self._created_states: list[CreatedState] = []
        # Track which (task_id, agent_id) combinations exist to avoid duplicates
        self._existing_combinations: set[tuple[str, str]] = set()

    @classmethod
    def generate(
        cls, num_tasks: int = 100, num_agents: int = 10, state_size: int = 100
    ) -> "TestData":
        """Generate test data for benchmarking."""
        return cls(
            task_ids=[generate_task_id() for _ in range(num_tasks)],
            agent_ids=[generate_agent_id() for _ in range(num_agents)],
            state_data=generate_state_data(state_size),
        )

    def random_task_id(self) -> str:
        return random.choice(self.task_ids)

    def random_agent_id(self) -> str:
        return random.choice(self.agent_ids)

    def get_unique_task_agent_pair(self) -> tuple[str, str]:
        """Get a unique (task_id, agent_id) pair for CREATE operations.

        Always generates a fresh UUID pair to avoid duplicate key errors.
        """
        # Always generate fresh IDs to guarantee uniqueness
        task_id = generate_task_id()
        agent_id = generate_agent_id()
        return task_id, agent_id

    def random_created_state_id(self) -> str | None:
        if not self._created_states:
            return None
        return random.choice(self._created_states).state_id

    def random_created_state(self) -> CreatedState | None:
        """Get a random created state with its task_id and agent_id."""
        if not self._created_states:
            return None
        return random.choice(self._created_states)

    def add_created_state(
        self, state_id: str, task_id: str | None = None, agent_id: str | None = None
    ) -> None:
        """Track a newly created state."""
        if task_id and agent_id:
            self._created_states.append(
                CreatedState(
                    state_id=state_id,
                    task_id=task_id,
                    agent_id=agent_id,
                )
            )
            self._existing_combinations.add((task_id, agent_id))
        else:
            # Legacy support - just track the ID
            self._created_states.append(
                CreatedState(
                    state_id=state_id,
                    task_id="",
                    agent_id="",
                )
            )

    def remove_created_state(self, state_id: str) -> None:
        """Remove a state from tracking after deletion."""
        for i, state in enumerate(self._created_states):
            if state.state_id == state_id:
                if state.task_id and state.agent_id:
                    self._existing_combinations.discard((state.task_id, state.agent_id))
                self._created_states.pop(i)
                break

    @property
    def created_state_ids(self) -> list[str]:
        """Get all created state IDs (for backwards compatibility)."""
        return [s.state_id for s in self._created_states]


# Operation weights for realistic load simulation
# Based on expected production usage patterns
OPERATION_WEIGHTS = {
    Operation.GET_BY_TASK_AGENT: 40,  # Most common - agents reading their state
    Operation.UPDATE: 25,  # Frequent - agents updating state
    Operation.CREATE: 15,  # Moderate - new task states
    Operation.LIST_BY_TASK: 10,  # Occasional - listing states
    Operation.GET_BY_ID: 5,  # Rare - direct ID lookups
    Operation.LIST_BY_AGENT: 3,  # Rare - agent-based queries
    Operation.DELETE: 2,  # Rare - cleanup operations
}


def weighted_operation_choice() -> Operation:
    """Choose an operation based on weights."""
    ops = list(OPERATION_WEIGHTS.keys())
    weights = list(OPERATION_WEIGHTS.values())
    return random.choices(ops, weights=weights, k=1)[0]
