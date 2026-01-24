"""
Locust load test for task state API endpoints.

This tests the full API stack including authentication and network overhead.

Usage:
    # Start Locust web UI
    CLUSTER_API_URL=https://dev.example.com API_KEY=your-key \
        locust -f scripts/benchmarks/locustfile.py

    # Headless mode for scripted testing
    CLUSTER_API_URL=https://dev.example.com API_KEY=your-key \
        locust -f scripts/benchmarks/locustfile.py \
        --headless -u 100 -r 10 -t 60s \
        --csv=results/locust_output

Environment Variables:
    CLUSTER_API_URL: Base URL of the API (required)
    API_KEY: API key for authentication (required)
    STATE_SIZE: Size of state data in bytes (default: 1000)
"""

import json
import os
import random
import string
import uuid
from typing import Any

from locust import HttpUser, between, task


def generate_state_data(size_bytes: int = 1000) -> dict[str, Any]:
    """Generate state data of approximately the target size."""
    base = {"key": "value", "metadata": {"created_by": "locust"}}
    base_size = len(json.dumps(base).encode("utf-8"))
    padding_needed = max(0, size_bytes - base_size)
    padding = "".join(
        random.choices(string.ascii_letters + string.digits, k=padding_needed)
    )
    return {
        "key": "value",
        "metadata": {"created_by": "locust", "version": 1},
        "data": padding,
    }


class TaskStateUser(HttpUser):
    """
    Simulates a user/agent interacting with task state endpoints.

    Task weights are based on expected production usage patterns:
    - get_state_by_task_and_agent: Most common (agents reading their state)
    - create_state: Frequent (new task initialization)
    - update_state: Frequent (agents updating progress)
    - list_states_by_task: Occasional (viewing task overview)
    - delete_state: Rare (cleanup)
    """

    # Wait between requests (simulate realistic user behavior)
    wait_time = between(0.1, 0.5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = os.environ.get("API_KEY", "")
        self.state_size = int(os.environ.get("STATE_SIZE", "1000"))

        # Track created states for this user
        self.created_state_ids: list[str] = []
        self.task_ids: list[str] = []
        self.agent_ids: list[str] = []

        # Pre-generate some IDs
        for _ in range(10):
            self.task_ids.append(str(uuid.uuid4()))
            self.agent_ids.append(str(uuid.uuid4()))

    def on_start(self):
        """Called when user starts - verify connection and create initial states."""
        # Verify API is accessible
        response = self.client.get(
            "/states",
            headers=self._auth_headers(),
            params={"limit": 1},
            name="health_check",
        )
        if response.status_code != 200:
            print(f"Warning: Initial health check failed: {response.status_code}")

        # Pre-create some states for read/update/delete operations
        for _ in range(5):
            self._create_state_internal()

    def _auth_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    def _random_task_id(self) -> str:
        return random.choice(self.task_ids)

    def _random_agent_id(self) -> str:
        return random.choice(self.agent_ids)

    def _random_state_id(self) -> str | None:
        if not self.created_state_ids:
            return None
        return random.choice(self.created_state_ids)

    def _create_state_internal(self) -> str | None:
        """Create a state and track it (internal helper)."""
        task_id = self._random_task_id()
        agent_id = self._random_agent_id()

        response = self.client.post(
            "/states",
            headers=self._auth_headers(),
            json={
                "task_id": task_id,
                "agent_id": agent_id,
                "state": generate_state_data(self.state_size),
            },
            name="create_state",
        )

        if response.status_code == 200:
            data = response.json()
            state_id = data.get("id")
            if state_id:
                self.created_state_ids.append(state_id)
                return state_id
        return None

    @task(10)
    def get_state_by_task_and_agent(self):
        """
        Get state by task_id and agent_id combination.
        This is the most common operation - agents checking their state.
        """
        task_id = self._random_task_id()
        agent_id = self._random_agent_id()

        self.client.get(
            "/states",
            headers=self._auth_headers(),
            params={
                "task_id": task_id,
                "agent_id": agent_id,
                "limit": 1,
            },
            name="get_state_by_task_agent",
        )

    @task(5)
    def create_state(self):
        """Create a new state."""
        self._create_state_internal()

    @task(3)
    def update_state(self):
        """Update an existing state."""
        state_id = self._random_state_id()
        if not state_id:
            return

        # First get the current state
        get_response = self.client.get(
            f"/states/{state_id}",
            headers=self._auth_headers(),
            name="get_state_for_update",
        )

        if get_response.status_code != 200:
            # State might have been deleted, remove from tracking
            if state_id in self.created_state_ids:
                self.created_state_ids.remove(state_id)
            return

        current_state = get_response.json()

        # Update the state
        self.client.put(
            f"/states/{state_id}",
            headers=self._auth_headers(),
            json={
                "task_id": current_state.get("task_id"),
                "agent_id": current_state.get("agent_id"),
                "state": generate_state_data(self.state_size),
            },
            name="update_state",
        )

    @task(3)
    def list_states_by_task(self):
        """List states filtered by task_id."""
        task_id = self._random_task_id()

        self.client.get(
            "/states",
            headers=self._auth_headers(),
            params={
                "task_id": task_id,
                "limit": 50,
            },
            name="list_states_by_task",
        )

    @task(1)
    def delete_state(self):
        """Delete a state."""
        state_id = self._random_state_id()
        if not state_id:
            return

        response = self.client.delete(
            f"/states/{state_id}",
            headers=self._auth_headers(),
            name="delete_state",
        )

        # Remove from tracking regardless of response
        if state_id in self.created_state_ids:
            self.created_state_ids.remove(state_id)

        # If successful, create a new state to maintain pool
        if response.status_code == 200:
            self._create_state_internal()


class ReadHeavyUser(HttpUser):
    """
    User profile simulating read-heavy workload (90% reads).
    Use for testing read replica scenarios.
    """

    wait_time = between(0.05, 0.2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = os.environ.get("API_KEY", "")
        self.task_ids = [str(uuid.uuid4()) for _ in range(50)]
        self.agent_ids = [str(uuid.uuid4()) for _ in range(10)]

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    @task(9)
    def get_state(self):
        """Read state by task and agent."""
        self.client.get(
            "/states",
            headers=self._auth_headers(),
            params={
                "task_id": random.choice(self.task_ids),
                "agent_id": random.choice(self.agent_ids),
                "limit": 1,
            },
            name="read_state",
        )

    @task(1)
    def list_states(self):
        """List states."""
        self.client.get(
            "/states",
            headers=self._auth_headers(),
            params={
                "task_id": random.choice(self.task_ids),
                "limit": 20,
            },
            name="list_states",
        )


# Default user class for locust
# To use ReadHeavyUser, run with: locust -f locustfile.py ReadHeavyUser
