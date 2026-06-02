"""
Integration tests documenting the task-name uniqueness / dedup behavior.

Background
----------
Task creation via the ACP ``task/create`` RPC runs through ``_get_or_create_task``
in ``agents_acp_use_case``. That helper looks an existing task up *by name* and
returns it if found, so re-using a task name silently returns the previously
created task (with its prior message history) instead of a new one. The behavior
is backed by a **global** ``unique`` constraint on ``tasks.name`` (see
``TaskORM`` in ``src/adapters/orm.py``).

The "same name returns the same task" half of that contract is already locked by
``test_handle_task_create_ignores_task_metadata_for_existing_task`` in the unit
suite (it asserts ``second.id == first.id``).

These tests cover the *database-level* facts that drive that behavior and that
can only be confirmed against real Postgres (testcontainers), namely:

1. Re-using a task name is rejected at the DB layer (the constraint that makes
   the use-case-level get-or-create reuse a row).
2. Omitting the name (``name=None``) always yields a brand-new task -- Postgres
   does not apply a unique constraint to NULLs -- so "omit name to always get a
   fresh task" genuinely works.
3. The uniqueness is **global**, not scoped per-agent: the same name cannot be
   used across two different agents.
"""

import pytest
import pytest_asyncio
from src.adapters.crud_store.exceptions import DuplicateItemError
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestTaskNameUniqueness:
    """Integration tests for the global uniqueness of ``tasks.name``."""

    @pytest_asyncio.fixture
    async def agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        return await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="uniqueness-test-agent",
                description="Agent for task-name uniqueness tests",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            )
        )

    async def test_duplicate_name_is_rejected(self, isolated_repositories, agent):
        """Two tasks with the same name cannot coexist.

        This is the constraint that the use-case-level get-or-create relies on:
        rather than let this error surface, ``_get_or_create_task`` looks the
        existing task up by name and returns it (the "stale task" footgun).
        """
        task_repo = isolated_repositories["task_repository"]

        await task_repo.create(
            agent_id=agent.id,
            task=TaskEntity(
                id=orm_id(),
                name="duplicate-name",
                status=TaskStatus.RUNNING,
            ),
        )

        # Second create with the *same* name -> DB unique constraint fires.
        with pytest.raises(DuplicateItemError):
            await task_repo.create(
                agent_id=agent.id,
                task=TaskEntity(
                    id=orm_id(),  # different id...
                    name="duplicate-name",  # ...same name
                    status=TaskStatus.RUNNING,
                ),
            )

    async def test_null_names_always_create_new_tasks(
        self, isolated_repositories, agent
    ):
        """Omitting the name (``name=None``) yields a fresh task every time.

        Postgres does not enforce a unique constraint across NULL values, so
        repeated name-less creates never collide. This confirms the "just omit
        name to always get a new task" path is real.
        """
        task_repo = isolated_repositories["task_repository"]

        first = await task_repo.create(
            agent_id=agent.id,
            task=TaskEntity(id=orm_id(), name=None, status=TaskStatus.RUNNING),
        )
        second = await task_repo.create(
            agent_id=agent.id,
            task=TaskEntity(id=orm_id(), name=None, status=TaskStatus.RUNNING),
        )

        # Two distinct tasks, both name-less, no collision.
        assert first.id != second.id
        assert first.name is None
        assert second.name is None

    async def test_name_uniqueness_is_global_not_per_agent(self, isolated_repositories):
        """The same name cannot be used across two different agents.

        The unique constraint is on ``tasks.name`` alone (no ``agent_id`` in the
        key), so task names share one global keyspace across every agent on the
        platform.
        """
        agent_repo = isolated_repositories["agent_repository"]
        task_repo = isolated_repositories["task_repository"]

        agent_a = await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="agent-a",
                description="Agent A",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            )
        )
        agent_b = await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="agent-b",
                description="Agent B",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            )
        )

        await task_repo.create(
            agent_id=agent_a.id,
            task=TaskEntity(
                id=orm_id(),
                name="shared-task-name",
                status=TaskStatus.RUNNING,
            ),
        )

        # Same name, *different* agent -> still rejected (global uniqueness).
        with pytest.raises(DuplicateItemError):
            await task_repo.create(
                agent_id=agent_b.id,
                task=TaskEntity(
                    id=orm_id(),
                    name="shared-task-name",
                    status=TaskStatus.RUNNING,
                ),
            )
