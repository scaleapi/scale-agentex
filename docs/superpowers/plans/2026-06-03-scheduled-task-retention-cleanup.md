# Scheduled Task-Retention Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Temporal Schedule + sweep workflow to the agentex backend that periodically discovers idle tasks for an allowlisted set of agents and runs the existing idempotent `clean_task` path against them, gated by a feature flag.

**Architecture:** A daily Temporal Schedule starts a `RetentionCleanupSweepWorkflow`. The sweep calls a `find_cleanup_candidates` activity (cheap, index-friendly Postgres pre-filter: `cleaned_at IS NULL AND updated_at < cutoff`, joined to an agent-name allowlist, keyset-paginated), then fans out one `RetentionCleanupTaskWorkflow` child per task. Each child calls a `clean_task` activity that delegates to the already-merged `TaskRetentionUseCase.clean_task`; the activity catches `ClientError` (the three safety/policy refusals) and maps it to a `skipped` outcome, so only genuine transient errors retry. The parent aggregates `cleaned`/`skipped`/`failed` counts and `continue_as_new`s per page to bound history.

**Tech Stack:** Python 3.12, Temporal (`temporalio`), SQLAlchemy async, FastAPI DI patterns, pytest (`pytest-asyncio`), testcontainers for integration.

**Spec:** `docs/superpowers/specs/2026-06-03-scheduled-task-retention-cleanup-design.md`

**Conventions to follow:**
- Run a single test: `make test FILE=tests/unit/path/test_foo.py NAME=test_name` (from `agentex/`).
- Lint before commit: `uv run ruff check src/ --fix && uv run ruff format src/` (from `agentex/`).
- Activity/workflow boundary carries **only JSON-native types** (`str`, `int`, `bool`, `list`, `dict`). The backend's Temporal data converter only adds datetime support (`client_factory.py:DateTimePayloadConverter`); it does NOT serialize Pydantic models. Cross the activity boundary with dicts; build Pydantic models (if any) inside domain code only.
- Commit messages: no Claude attribution (repo is public — see `CLAUDE.md`).

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `agentex/src/config/environment_variables.py` | Modify | Add the 6 `RETENTION_CLEANUP_*` config fields + parsing. |
| `agentex/src/domain/repositories/task_repository.py` | Modify | Add `list_cleanup_candidate_ids(...)` keyset-paginated discovery query. |
| `agentex/src/temporal/task_retention_factory.py` | Create | `build_task_retention_use_case(...)` — wires `TaskRetentionUseCase` outside FastAPI DI. |
| `agentex/src/temporal/activities/retention_cleanup_activities.py` | Create | `RetentionCleanupActivities` with `find_cleanup_candidates` + `clean_task` activities. |
| `agentex/src/temporal/workflows/retention_cleanup_workflow.py` | Create | `RetentionCleanupSweepWorkflow` (fan-out + paging) + `RetentionCleanupTaskWorkflow` (per-task child). |
| `agentex/src/temporal/run_worker.py` | Modify | Register the new workflows + activities on the `agentex-server` queue. |
| `agentex/src/temporal/run_retention_cleanup_schedule.py` | Create | Startup script: create/update the Temporal Schedule when enabled. |
| `agentex/docker-compose.yml` | Modify | Add the schedule-bootstrap step + env vars for local dev. |
| `agentex/tests/unit/temporal/test_retention_cleanup_activities.py` | Create | Unit tests for the activities (mocked use case / repo). |
| `agentex/tests/unit/temporal/test_retention_cleanup_workflow.py` | Create | Workflow tests via `WorkflowEnvironment` with mocked activities. |
| `agentex/tests/unit/config/test_retention_cleanup_env.py` | Create | Env-var parsing test. |
| `agentex/tests/integration/test_retention_cleanup_discovery.py` | Create | Integration test for `list_cleanup_candidate_ids` against real Postgres. |

---

## Task 1: Add retention-cleanup configuration

**Files:**
- Modify: `agentex/src/config/environment_variables.py`
- Test: `agentex/tests/unit/config/test_retention_cleanup_env.py`

- [ ] **Step 1: Write the failing test**

Create `agentex/tests/unit/config/test_retention_cleanup_env.py`:

```python
import pytest

from src.config.environment_variables import EnvironmentVariables


@pytest.mark.unit
def test_retention_cleanup_env_parses_enabled_and_allowlist(monkeypatch):
    monkeypatch.setenv("RETENTION_CLEANUP_ENABLED", "true")
    monkeypatch.setenv("RETENTION_CLEANUP_AGENT_ALLOWLIST", "agent-a, agent-b ,agent-c")
    monkeypatch.setenv("RETENTION_CLEANUP_IDLE_DAYS", "14")
    monkeypatch.setenv("RETENTION_CLEANUP_CRON", "0 3 * * *")
    monkeypatch.setenv("RETENTION_CLEANUP_PAGE_SIZE", "50")
    monkeypatch.setenv("RETENTION_CLEANUP_MAX_IN_FLIGHT", "5")

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_ENABLED is True
    # Allowlist is parsed into a trimmed, non-empty list of names.
    assert env.RETENTION_CLEANUP_AGENT_ALLOWLIST == ["agent-a", "agent-b", "agent-c"]
    assert env.RETENTION_CLEANUP_IDLE_DAYS == 14
    assert env.RETENTION_CLEANUP_CRON == "0 3 * * *"
    assert env.RETENTION_CLEANUP_PAGE_SIZE == 50
    assert env.RETENTION_CLEANUP_MAX_IN_FLIGHT == 5


@pytest.mark.unit
def test_retention_cleanup_env_defaults(monkeypatch):
    for key in (
        "RETENTION_CLEANUP_ENABLED",
        "RETENTION_CLEANUP_AGENT_ALLOWLIST",
        "RETENTION_CLEANUP_IDLE_DAYS",
        "RETENTION_CLEANUP_CRON",
        "RETENTION_CLEANUP_PAGE_SIZE",
        "RETENTION_CLEANUP_MAX_IN_FLIGHT",
    ):
        monkeypatch.delenv(key, raising=False)

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_ENABLED is False
    assert env.RETENTION_CLEANUP_AGENT_ALLOWLIST == []  # fail-closed
    assert env.RETENTION_CLEANUP_IDLE_DAYS == 7
    assert env.RETENTION_CLEANUP_CRON == "0 4 * * *"
    assert env.RETENTION_CLEANUP_PAGE_SIZE == 200
    assert env.RETENTION_CLEANUP_MAX_IN_FLIGHT == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test FILE=tests/unit/config/test_retention_cleanup_env.py`
Expected: FAIL — `AttributeError` / unexpected attribute on `EnvironmentVariables`.

- [ ] **Step 3: Implement the config**

In `agentex/src/config/environment_variables.py`, add to the `EnvVarKeys` class (near `ENABLE_HEALTH_CHECK_WORKFLOW`, line ~59):

```python
    RETENTION_CLEANUP_ENABLED = "RETENTION_CLEANUP_ENABLED"
    RETENTION_CLEANUP_AGENT_ALLOWLIST = "RETENTION_CLEANUP_AGENT_ALLOWLIST"
    RETENTION_CLEANUP_IDLE_DAYS = "RETENTION_CLEANUP_IDLE_DAYS"
    RETENTION_CLEANUP_CRON = "RETENTION_CLEANUP_CRON"
    RETENTION_CLEANUP_PAGE_SIZE = "RETENTION_CLEANUP_PAGE_SIZE"
    RETENTION_CLEANUP_MAX_IN_FLIGHT = "RETENTION_CLEANUP_MAX_IN_FLIGHT"
```

Add the fields to the `EnvironmentVariables` model (near `ENABLE_HEALTH_CHECK_WORKFLOW`, line ~115):

```python
    RETENTION_CLEANUP_ENABLED: bool = False
    RETENTION_CLEANUP_AGENT_ALLOWLIST: list[str] = []
    RETENTION_CLEANUP_IDLE_DAYS: int = 7
    RETENTION_CLEANUP_CRON: str = "0 4 * * *"
    RETENTION_CLEANUP_PAGE_SIZE: int = 200
    RETENTION_CLEANUP_MAX_IN_FLIGHT: int = 20
```

Add the parsing inside `refresh()` where the `EnvironmentVariables(...)` instance is built (alongside `ENABLE_HEALTH_CHECK_WORKFLOW=...`, line ~199):

```python
            RETENTION_CLEANUP_ENABLED=(
                os.environ.get(EnvVarKeys.RETENTION_CLEANUP_ENABLED, "false") == "true"
            ),
            RETENTION_CLEANUP_AGENT_ALLOWLIST=[
                name.strip()
                for name in os.environ.get(
                    EnvVarKeys.RETENTION_CLEANUP_AGENT_ALLOWLIST, ""
                ).split(",")
                if name.strip()
            ],
            RETENTION_CLEANUP_IDLE_DAYS=int(
                os.environ.get(EnvVarKeys.RETENTION_CLEANUP_IDLE_DAYS, "7")
            ),
            RETENTION_CLEANUP_CRON=os.environ.get(
                EnvVarKeys.RETENTION_CLEANUP_CRON, "0 4 * * *"
            ),
            RETENTION_CLEANUP_PAGE_SIZE=int(
                os.environ.get(EnvVarKeys.RETENTION_CLEANUP_PAGE_SIZE, "200")
            ),
            RETENTION_CLEANUP_MAX_IN_FLIGHT=int(
                os.environ.get(EnvVarKeys.RETENTION_CLEANUP_MAX_IN_FLIGHT, "20")
            ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test FILE=tests/unit/config/test_retention_cleanup_env.py`
Expected: PASS (both tests).

- [ ] **Step 5: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/config/environment_variables.py tests/unit/config/test_retention_cleanup_env.py
git commit -m "feat(retention): add scheduled-cleanup configuration env vars"
```

---

## Task 2: Discovery query — `list_cleanup_candidate_ids`

**Files:**
- Modify: `agentex/src/domain/repositories/task_repository.py`
- Test: `agentex/tests/integration/test_retention_cleanup_discovery.py`

- [ ] **Step 1: Write the failing integration test**

Create `agentex/tests/integration/test_retention_cleanup_discovery.py`. It seeds rows directly via SQLAlchemy core (so we can control `updated_at` / `cleaned_at`), then asserts the query's filtering and keyset paging.

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert

from src.adapters.orm import AgentORM, TaskAgentORM, TaskORM
from src.domain.entities.tasks import TaskStatus


async def _seed_agent(session, agent_id: str, name: str) -> None:
    await session.execute(
        insert(AgentORM).values(
            id=agent_id,
            name=name,
            description="seed",
            acp_url=f"http://{agent_id}:8000",
            acp_type="sync",
        )
    )


async def _seed_task(
    session,
    *,
    task_id: str,
    agent_id: str,
    updated_at: datetime,
    cleaned_at: datetime | None,
    status: TaskStatus = TaskStatus.COMPLETED,
) -> None:
    await session.execute(
        insert(TaskORM).values(
            id=task_id,
            name=task_id,
            status=status,
            updated_at=updated_at,
            cleaned_at=cleaned_at,
        )
    )
    await session.execute(
        insert(TaskAgentORM).values(task_id=task_id, agent_id=agent_id)
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_filters_and_keyset_paging(isolated_repositories):
    repo = isolated_repositories["task_repository"]
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    async with isolated_repositories["postgres_rw_session_factory"]() as session:
        await _seed_agent(session, "agent-allowed", "allowed-agent")
        await _seed_agent(session, "agent-other", "other-agent")
        # idle + allowlisted + not cleaned -> eligible
        await _seed_task(session, task_id="t-aaa", agent_id="agent-allowed", updated_at=old, cleaned_at=None)
        await _seed_task(session, task_id="t-bbb", agent_id="agent-allowed", updated_at=old, cleaned_at=None)
        # recently active (updated_at recent) -> excluded by pre-filter
        await _seed_task(session, task_id="t-fresh", agent_id="agent-allowed", updated_at=now, cleaned_at=None)
        # already cleaned -> excluded
        await _seed_task(session, task_id="t-clean", agent_id="agent-allowed", updated_at=old, cleaned_at=old)
        # idle but NOT on allowlist -> excluded
        await _seed_task(session, task_id="t-other", agent_id="agent-other", updated_at=old, cleaned_at=None)
        await session.commit()

    # Full page: only the two eligible ids, ordered by id ascending.
    ids = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=["allowed-agent"], after_id=None, limit=100
    )
    assert ids == ["t-aaa", "t-bbb"]

    # Keyset paging: limit=1 then resume after the first id.
    page1 = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=["allowed-agent"], after_id=None, limit=1
    )
    assert page1 == ["t-aaa"]
    page2 = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=["allowed-agent"], after_id="t-aaa", limit=1
    )
    assert page2 == ["t-bbb"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_empty_allowlist_returns_nothing(isolated_repositories):
    repo = isolated_repositories["task_repository"]
    ids = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=[], after_id=None, limit=100
    )
    assert ids == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test FILE=tests/integration/test_retention_cleanup_discovery.py`
Expected: FAIL — `AttributeError: 'TaskRepository' object has no attribute 'list_cleanup_candidate_ids'`.

- [ ] **Step 3: Implement the query method**

In `agentex/src/domain/repositories/task_repository.py`, add the import at the top (the module already imports `select`, `update` from sqlalchemy and `Sequence` from collections.abc):

```python
from datetime import UTC, datetime, timedelta
```

Add this method to `TaskRepository` (e.g. right after `list_with_join`):

```python
    async def list_cleanup_candidate_ids(
        self,
        *,
        idle_days: int,
        agent_names: Sequence[str],
        after_id: str | None,
        limit: int,
    ) -> list[str]:
        """
        Return ids of tasks eligible for scheduled retention cleanup.

        Cheap, index-friendly PRE-FILTER only — the authoritative idle / status /
        unprocessed-events checks live in TaskRetentionService.clean_task. This
        deliberately omits a status filter: status is race-prone (a task can flip
        to RUNNING between this query and the clean call), so the trustworthy
        RUNNING guard is enforced at clean-time. `updated_at < cutoff` is a correct
        superset of truly-idle tasks (true idleness also requires the latest Mongo
        message to predate the cutoff), so we never under-include.

        Keyset-paginated by id ascending; pass the last returned id as `after_id`
        to fetch the next page. Fail-closed: empty `agent_names` returns [].
        """
        if not agent_names:
            return []

        cutoff = datetime.now(UTC) - timedelta(days=idle_days)
        query = (
            select(TaskORM.id)
            .join(TaskAgentORM, TaskORM.id == TaskAgentORM.task_id)
            .join(AgentORM, TaskAgentORM.agent_id == AgentORM.id)
            .where(
                TaskORM.cleaned_at.is_(None),
                TaskORM.updated_at < cutoff,
                AgentORM.name.in_(list(agent_names)),
            )
            .order_by(TaskORM.id.asc())
            .limit(limit)
            .distinct()
        )
        if after_id is not None:
            query = query.where(TaskORM.id > after_id)

        async with self.start_async_db_session(False) as session:
            result = await session.execute(query)
            return [row[0] for row in result.all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test FILE=tests/integration/test_retention_cleanup_discovery.py`
Expected: PASS (both tests).

> If the `AgentORM` / `TaskORM` inserts fail on a NOT NULL column, add the missing
> column to the corresponding `_seed_*` helper using the column's value from
> `src/adapters/orm.py` — do not change the query.

- [ ] **Step 5: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/domain/repositories/task_repository.py tests/integration/test_retention_cleanup_discovery.py
git commit -m "feat(retention): add keyset-paginated cleanup-candidate discovery query"
```

---

## Task 3: Use-case factory for worker context

**Files:**
- Create: `agentex/src/temporal/task_retention_factory.py`

No dedicated test (it's pure wiring exercised by Task 4's tests and at runtime). Verified against real constructor signatures:
`TaskRepository`/`EventRepository`/`AgentTaskTrackerRepository(rw_maker, ro_maker)`,
`TaskMessageRepository(db)`, `TaskStateRepository(db)`, `TaskMessageService(message_repository=...)`,
`TemporalAdapter(temporal_client=...)`, `TaskRetentionService(...)`, `TaskRetentionUseCase(retention_service=...)`.

- [ ] **Step 1: Create the factory**

Create `agentex/src/temporal/task_retention_factory.py`:

```python
"""
Construct a TaskRetentionUseCase outside FastAPI's Depends DI, for use inside
Temporal worker processes. Mirrors the manual-wiring pattern in
run_healthcheck_workflow.py (repositories built from session makers).
"""

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
    httpx_client,
)
from src.domain.repositories.agent_task_tracker_repository import (
    AgentTaskTrackerRepository,
)
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_message_repository import TaskMessageRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.task_state_repository import TaskStateRepository
from src.domain.services.task_message_service import TaskMessageService
from src.domain.services.task_retention_service import TaskRetentionService
from src.domain.use_cases.task_retention_use_case import TaskRetentionUseCase


def build_task_retention_use_case(
    global_dependencies: GlobalDependencies,
) -> TaskRetentionUseCase:
    """Wire a TaskRetentionUseCase from an already-loaded GlobalDependencies."""
    engine = database_async_read_write_engine()
    rw_session_maker = database_async_read_write_session_maker(engine)
    ro_session_maker = database_async_read_only_session_maker(engine)

    task_repository = TaskRepository(rw_session_maker, ro_session_maker)
    event_repository = EventRepository(rw_session_maker, ro_session_maker)
    agent_task_tracker_repository = AgentTaskTrackerRepository(
        rw_session_maker, ro_session_maker
    )

    task_message_repository = TaskMessageRepository(global_dependencies.mongodb_database)
    task_state_repository = TaskStateRepository(global_dependencies.mongodb_database)
    task_message_service = TaskMessageService(message_repository=task_message_repository)

    temporal_adapter = TemporalAdapter(
        temporal_client=global_dependencies.temporal_client
    )

    retention_service = TaskRetentionService(
        task_repository=task_repository,
        task_message_service=task_message_service,
        task_message_repository=task_message_repository,
        task_state_repository=task_state_repository,
        event_repository=event_repository,
        agent_task_tracker_repository=agent_task_tracker_repository,
        temporal_adapter=temporal_adapter,
        httpx_client=httpx_client(),
    )
    return TaskRetentionUseCase(retention_service=retention_service)
```

- [ ] **Step 2: Verify it imports**

Run: `cd agentex && uv run python -c "from src.temporal.task_retention_factory import build_task_retention_use_case; print('ok')"`
Expected: prints `ok` (no ImportError).

- [ ] **Step 3: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/temporal/task_retention_factory.py
git commit -m "feat(retention): add worker-context factory for TaskRetentionUseCase"
```

---

## Task 4: Cleanup activities

**Files:**
- Create: `agentex/src/temporal/activities/retention_cleanup_activities.py`
- Test: `agentex/tests/unit/temporal/test_retention_cleanup_activities.py`

The activities cross the Temporal boundary with JSON-native types only. `clean_task`
returns a dict: `{"task_id", "status": "cleaned"|"skipped", "reason", "messages_deleted", "task_states_deleted", "events_deleted"}`.

- [ ] **Step 1: Write the failing tests**

Create `agentex/tests/unit/temporal/test_retention_cleanup_activities.py`:

```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.domain.entities.task_retention import TaskCleanupResultEntity
from src.domain.exceptions import ClientError
from src.temporal.activities.retention_cleanup_activities import (
    RetentionCleanupActivities,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_cleanup_candidates_delegates_to_repo():
    repo = AsyncMock()
    repo.list_cleanup_candidate_ids.return_value = ["t1", "t2"]
    activities = RetentionCleanupActivities(task_repository=repo, use_case=AsyncMock())

    result = await activities.find_cleanup_candidates(
        after_id=None, limit=200, idle_days=7, agent_names=["a"]
    )

    assert result == ["t1", "t2"]
    repo.list_cleanup_candidate_ids.assert_awaited_once_with(
        idle_days=7, agent_names=["a"], after_id=None, limit=200
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_cleaned_outcome():
    use_case = AsyncMock()
    use_case.clean_task.return_value = TaskCleanupResultEntity(
        task_id="t1",
        cleaned_at=datetime.now(UTC),
        messages_deleted=3,
        task_states_deleted=1,
        events_deleted=2,
    )
    activities = RetentionCleanupActivities(task_repository=AsyncMock(), use_case=use_case)

    outcome = await activities.clean_task(task_id="t1", idle_days=7)

    assert outcome["status"] == "cleaned"
    assert outcome["task_id"] == "t1"
    assert outcome["messages_deleted"] == 3
    use_case.clean_task.assert_awaited_once_with(task_id="t1", force=False, idle_days=7)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_clienterror_maps_to_skipped():
    use_case = AsyncMock()
    use_case.clean_task.side_effect = ClientError("Cannot clean task t1: status is RUNNING (active)")
    activities = RetentionCleanupActivities(task_repository=AsyncMock(), use_case=use_case)

    outcome = await activities.clean_task(task_id="t1", idle_days=7)

    assert outcome["status"] == "skipped"
    assert "RUNNING" in outcome["reason"]
    assert outcome["task_id"] == "t1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_unexpected_error_propagates():
    use_case = AsyncMock()
    use_case.clean_task.side_effect = RuntimeError("mongo timeout")
    activities = RetentionCleanupActivities(task_repository=AsyncMock(), use_case=use_case)

    with pytest.raises(RuntimeError):
        await activities.clean_task(task_id="t1", idle_days=7)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `make test FILE=tests/unit/temporal/test_retention_cleanup_activities.py`
Expected: FAIL — module `retention_cleanup_activities` does not exist.

- [ ] **Step 3: Implement the activities**

Create `agentex/src/temporal/activities/retention_cleanup_activities.py`:

```python
"""
Temporal activities for the scheduled task-retention cleanup sweep.

Two activities:
- find_cleanup_candidates: cheap pre-filtered, keyset-paginated discovery.
- clean_task: delegates to TaskRetentionUseCase.clean_task; catches ClientError
  (the three policy/safety refusals) and maps it to a 'skipped' outcome so the
  caller's child workflow completes cleanly. Genuine transient errors propagate
  so Temporal retries them.

Boundary types are JSON-native (the backend data converter does not serialize
Pydantic models).
"""

from src.domain.exceptions import ClientError
from src.domain.repositories.task_repository import TaskRepository
from src.domain.use_cases.task_retention_use_case import TaskRetentionUseCase
from src.utils.logging import make_logger
from temporalio import activity

logger = make_logger(__name__)

FIND_CLEANUP_CANDIDATES_ACTIVITY = "find_cleanup_candidates_activity"
CLEAN_TASK_ACTIVITY = "clean_task_activity"


class RetentionCleanupActivities:
    def __init__(
        self,
        task_repository: TaskRepository,
        use_case: TaskRetentionUseCase,
    ):
        self.task_repository = task_repository
        self.use_case = use_case

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def find_cleanup_candidates(
        self,
        after_id: str | None,
        limit: int,
        idle_days: int,
        agent_names: list[str],
    ) -> list[str]:
        return await self.task_repository.list_cleanup_candidate_ids(
            idle_days=idle_days,
            agent_names=agent_names,
            after_id=after_id,
            limit=limit,
        )

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def clean_task(self, task_id: str, idle_days: int) -> dict:
        try:
            result = await self.use_case.clean_task(
                task_id=task_id, force=False, idle_days=idle_days
            )
            return {
                "task_id": result.task_id,
                "status": "cleaned",
                "reason": None,
                "messages_deleted": result.messages_deleted,
                "task_states_deleted": result.task_states_deleted,
                "events_deleted": result.events_deleted,
            }
        except ClientError as e:
            # Expected policy/safety refusal (RUNNING / not idle / unprocessed
            # events). Backstop for the rare race the pre-filter can't catch.
            logger.info(
                "task_cleanup_skipped",
                extra={"task_id": task_id, "reason": str(e)},
            )
            return {
                "task_id": task_id,
                "status": "skipped",
                "reason": str(e),
                "messages_deleted": 0,
                "task_states_deleted": 0,
                "events_deleted": 0,
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make test FILE=tests/unit/temporal/test_retention_cleanup_activities.py`
Expected: PASS (all four).

- [ ] **Step 5: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/temporal/activities/retention_cleanup_activities.py tests/unit/temporal/test_retention_cleanup_activities.py
git commit -m "feat(retention): add cleanup discovery + clean activities"
```

---

## Task 5: Sweep + per-task child workflows

**Files:**
- Create: `agentex/src/temporal/workflows/retention_cleanup_workflow.py`
- Test: `agentex/tests/unit/temporal/test_retention_cleanup_workflow.py`

- [ ] **Step 1: Write the failing workflow test**

Create `agentex/tests/unit/temporal/test_retention_cleanup_workflow.py`. It runs the real workflows in a time-skipping `WorkflowEnvironment` with **mocked activities** so no DB is needed.

```python
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from src.temporal.activities.retention_cleanup_activities import (
    CLEAN_TASK_ACTIVITY,
    FIND_CLEANUP_CANDIDATES_ACTIVITY,
)
from src.temporal.workflows.retention_cleanup_workflow import (
    RetentionCleanupSweepWorkflow,
    RetentionCleanupTaskWorkflow,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sweep_cleans_all_pages_and_aggregates():
    # Two pages of candidates then empty; one task is skipped, one fails once then is counted failed.
    pages = {None: ["t1", "t2"], "t2": ["t3"], "t3": []}

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find(after_id, limit, idle_days, agent_names) -> list[str]:
        return pages[after_id]

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int) -> dict:
        if task_id == "t2":
            return {"task_id": task_id, "status": "skipped", "reason": "RUNNING",
                    "messages_deleted": 0, "task_states_deleted": 0, "events_deleted": 0}
        if task_id == "t3":
            raise RuntimeError("permanent failure")
        return {"task_id": task_id, "status": "cleaned", "reason": None,
                "messages_deleted": 1, "task_states_deleted": 0, "events_deleted": 0}

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-retention",
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[fake_find, fake_clean],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            summary = await env.client.execute_workflow(
                RetentionCleanupSweepWorkflow.run,
                {
                    "idle_days": 7,
                    "agent_names": ["a"],
                    "page_size": 2,
                    "max_in_flight": 2,
                },
                id=f"sweep-{uuid.uuid4()}",
                task_queue="test-retention",
            )

    assert summary["cleaned"] == 1   # t1
    assert summary["skipped"] == 1   # t2
    assert summary["failed"] == 1    # t3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make test FILE=tests/unit/temporal/test_retention_cleanup_workflow.py`
Expected: FAIL — module `retention_cleanup_workflow` does not exist.

- [ ] **Step 3: Implement the workflows**

Create `agentex/src/temporal/workflows/retention_cleanup_workflow.py`:

```python
"""
Scheduled task-retention cleanup workflows.

RetentionCleanupSweepWorkflow: started by a Temporal Schedule. Pulls one page of
candidate task ids, fans out one child workflow per task (bounded by
max_in_flight), aggregates cleaned/skipped/failed counts, then continue_as_new's
to the next page so workflow history stays bounded regardless of backlog size.

RetentionCleanupTaskWorkflow: per-task child. Invokes the clean activity, which
already maps the policy/safety ClientError refusals to a 'skipped' outcome; only
genuine transient errors surface as activity failures (and are retried).
"""

import asyncio
from datetime import timedelta

from src.temporal.activities.retention_cleanup_activities import (
    CLEAN_TASK_ACTIVITY,
    FIND_CLEANUP_CANDIDATES_ACTIVITY,
)
from src.utils.logging import make_logger
from temporalio import workflow
from temporalio.common import RetryPolicy

logger = make_logger(__name__)


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


@workflow.defn
class RetentionCleanupTaskWorkflow:
    @workflow.run
    async def run(self, args: dict) -> dict:
        return await workflow.execute_activity(
            CLEAN_TASK_ACTIVITY,
            args=[args["task_id"], args["idle_days"]],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )


@workflow.defn
class RetentionCleanupSweepWorkflow:
    @workflow.run
    async def run(self, args: dict) -> dict:
        idle_days = args["idle_days"]
        agent_names = args["agent_names"]
        page_size = args.get("page_size", 200)
        max_in_flight = args.get("max_in_flight", 20)
        after_id = args.get("after_id")
        totals = args.get("totals", {"cleaned": 0, "skipped": 0, "failed": 0})

        task_ids = await workflow.execute_activity(
            FIND_CLEANUP_CANDIDATES_ACTIVITY,
            args=[after_id, page_size, idle_days, agent_names],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )

        if not task_ids:
            logger.info("retention_cleanup_sweep_completed", extra=totals)
            return totals

        for batch in _chunked(task_ids, max_in_flight):
            results = await asyncio.gather(
                *[
                    workflow.execute_child_workflow(
                        RetentionCleanupTaskWorkflow.run,
                        {"task_id": task_id, "idle_days": idle_days},
                        id=f"retention-cleanup-task-{task_id}",
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    for task_id in batch
                ],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    totals["failed"] += 1
                else:
                    status = result.get("status", "failed")
                    totals[status] = totals.get(status, 0) + 1

        # Bound history: hand the next page to a fresh run.
        workflow.continue_as_new(
            {
                "idle_days": idle_days,
                "agent_names": agent_names,
                "page_size": page_size,
                "max_in_flight": max_in_flight,
                "after_id": task_ids[-1],
                "totals": totals,
            }
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `make test FILE=tests/unit/temporal/test_retention_cleanup_workflow.py`
Expected: PASS. (Note: `WorkflowEnvironment.start_time_skipping()` downloads a test server on first run; ensure network access. If `temporalio` test deps are missing, install with `uv sync`.)

- [ ] **Step 5: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/temporal/workflows/retention_cleanup_workflow.py tests/unit/temporal/test_retention_cleanup_workflow.py
git commit -m "feat(retention): add sweep + per-task cleanup workflows"
```

---

## Task 6: Register workflows + activities on the worker

**Files:**
- Modify: `agentex/src/temporal/run_worker.py`

- [ ] **Step 1: Add a worker factory for retention cleanup**

In `agentex/src/temporal/run_worker.py`, add imports near the existing imports:

```python
from src.config.dependencies import GlobalDependencies
from src.temporal.activities.retention_cleanup_activities import (
    RetentionCleanupActivities,
)
from src.temporal.task_retention_factory import build_task_retention_use_case
from src.temporal.workflows.retention_cleanup_workflow import (
    RetentionCleanupSweepWorkflow,
    RetentionCleanupTaskWorkflow,
)
from src.domain.repositories.task_repository import TaskRepository
```

Add this factory function (mirrors `create_health_check_worker`):

```python
def create_retention_cleanup_worker(
    global_dependencies: GlobalDependencies,
) -> asyncio.Task:
    """Create a worker that serves the retention-cleanup workflows + activities."""
    task_queue = os.environ.get("AGENTEX_SERVER_TASK_QUEUE", AGENTEX_SERVER_TASK_QUEUE)

    engine = database_async_read_write_engine()
    rw_session_maker = database_async_read_write_session_maker(engine)
    ro_session_maker = database_async_read_only_session_maker(engine)
    task_repository = TaskRepository(rw_session_maker, ro_session_maker)
    use_case = build_task_retention_use_case(global_dependencies)

    retention_activities = RetentionCleanupActivities(
        task_repository=task_repository,
        use_case=use_case,
    )

    return asyncio.create_task(
        run_worker(
            task_queue=task_queue,
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[
                retention_activities.find_cleanup_candidates,
                retention_activities.clean_task,
            ],
            max_workers=50,
            max_concurrent_activities=50,
        )
    )
```

> **Note on `run_worker`'s global `health_check_worker`:** the existing `run_worker`
> assigns the worker to a module global and shuts that single global down in
> `finally`. Running two `run_worker` tasks in one process would clobber that
> global. For v1 the retention worker runs as its **own process** (see Task 8 —
> a separate docker-compose service / k8s deployment invoking
> `create_retention_cleanup_worker` via a `main()`), so it does not share the
> health-check process. Add a `main()` to this module that loads
> `GlobalDependencies` and awaits `create_retention_cleanup_worker(...)`, guarded
> so it only runs when invoked as the retention entrypoint.

Add a retention entrypoint `main` (separate from the health-check `main`):

```python
async def run_retention_cleanup_worker_main() -> None:
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()
    worker_task = create_retention_cleanup_worker(global_dependencies)
    await worker_task
```

- [ ] **Step 2: Verify imports/compile**

Run: `cd agentex && uv run python -c "from src.temporal.run_worker import create_retention_cleanup_worker, run_retention_cleanup_worker_main; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/temporal/run_worker.py
git commit -m "feat(retention): register cleanup workflows + activities on worker"
```

---

## Task 7: Schedule bootstrap script

**Files:**
- Create: `agentex/src/temporal/run_retention_cleanup_schedule.py`

This mirrors `run_healthcheck_workflow.py`: a startup script that, when enabled,
creates (or no-ops if already present) the Temporal Schedule.

- [ ] **Step 1: Create the bootstrap script**

Create `agentex/src/temporal/run_retention_cleanup_schedule.py`:

```python
"""
Create the Temporal Schedule that drives the scheduled task-retention cleanup.

Runs at startup (mirrors run_healthcheck_workflow.py). No-op unless
RETENTION_CLEANUP_ENABLED is true and an agent allowlist is configured
(fail-closed). Idempotent: if the schedule already exists, it is left as-is.
"""

import asyncio

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.client_factory import TemporalClientFactory
from src.adapters.temporal.exceptions import TemporalScheduleAlreadyExistsError
from src.config.dependencies import GlobalDependencies
from src.config.environment_variables import EnvironmentVariables
from src.temporal.run_worker import AGENTEX_SERVER_TASK_QUEUE
from src.temporal.workflows.retention_cleanup_workflow import (
    RetentionCleanupSweepWorkflow,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

SCHEDULE_ID = "retention-cleanup-sweep"
WORKFLOW_ID = "retention-cleanup-sweep"


async def main() -> None:
    global_dependencies = GlobalDependencies()
    await global_dependencies.load()

    env = EnvironmentVariables.refresh()
    if not env or not env.RETENTION_CLEANUP_ENABLED:
        logger.info("Retention cleanup is not enabled; skipping schedule creation")
        return
    if not env.RETENTION_CLEANUP_AGENT_ALLOWLIST:
        logger.warning(
            "Retention cleanup enabled but agent allowlist is empty (fail-closed); "
            "skipping schedule creation"
        )
        return
    if not TemporalClientFactory.is_temporal_configured(env):
        logger.error("Temporal is not configured; skipping schedule creation")
        return

    task_queue = env.AGENTEX_SERVER_TASK_QUEUE or AGENTEX_SERVER_TASK_QUEUE
    adapter = TemporalAdapter(temporal_client=global_dependencies.temporal_client)

    workflow_args = {
        "idle_days": env.RETENTION_CLEANUP_IDLE_DAYS,
        "agent_names": env.RETENTION_CLEANUP_AGENT_ALLOWLIST,
        "page_size": env.RETENTION_CLEANUP_PAGE_SIZE,
        "max_in_flight": env.RETENTION_CLEANUP_MAX_IN_FLIGHT,
    }

    try:
        await adapter.create_schedule(
            schedule_id=SCHEDULE_ID,
            workflow=RetentionCleanupSweepWorkflow.run,
            workflow_id=WORKFLOW_ID,
            args=[workflow_args],
            task_queue=task_queue,
            cron_expressions=[env.RETENTION_CLEANUP_CRON],
        )
        logger.info(
            "Created retention-cleanup schedule",
            extra={"cron": env.RETENTION_CLEANUP_CRON, "args": workflow_args},
        )
    except TemporalScheduleAlreadyExistsError:
        logger.info("Retention-cleanup schedule already exists; leaving as-is")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify imports/compile**

Run: `cd agentex && uv run python -c "import src.temporal.run_retention_cleanup_schedule as m; print(m.SCHEDULE_ID)"`
Expected: prints `retention-cleanup-sweep`.

- [ ] **Step 3: Lint + commit**

```bash
cd agentex && uv run ruff check src/ --fix && uv run ruff format src/
git add src/temporal/run_retention_cleanup_schedule.py
git commit -m "feat(retention): add cleanup schedule bootstrap script"
```

---

## Task 8: Wire local dev (docker-compose) + docs

**Files:**
- Modify: `agentex/docker-compose.yml`

- [ ] **Step 1: Add the retention worker service + schedule bootstrap**

In `agentex/docker-compose.yml`, add a worker service modeled on the existing
`agentex-temporal-worker` service, but running the retention entrypoint, and add a
schedule-bootstrap invocation. Use the same image/build, env, and `depends_on` as
`agentex-temporal-worker`. Set its command to run the retention worker:

```yaml
  agentex-retention-cleanup-worker:
    # (copy build/image/env/depends_on/networks from agentex-temporal-worker)
    command: >-
      python -c "import asyncio; from src.temporal.run_worker import run_retention_cleanup_worker_main; asyncio.run(run_retention_cleanup_worker_main())"
    environment:
      # inherit the temporal-worker env, plus:
      RETENTION_CLEANUP_ENABLED: "${RETENTION_CLEANUP_ENABLED:-false}"
      RETENTION_CLEANUP_AGENT_ALLOWLIST: "${RETENTION_CLEANUP_AGENT_ALLOWLIST:-}"
      RETENTION_CLEANUP_IDLE_DAYS: "${RETENTION_CLEANUP_IDLE_DAYS:-7}"
      RETENTION_CLEANUP_CRON: "${RETENTION_CLEANUP_CRON:-0 4 * * *}"
      RETENTION_CLEANUP_PAGE_SIZE: "${RETENTION_CLEANUP_PAGE_SIZE:-200}"
      RETENTION_CLEANUP_MAX_IN_FLIGHT: "${RETENTION_CLEANUP_MAX_IN_FLIGHT:-20}"
```

Add the schedule bootstrap to the `agentex` API service startup command, right
after the health-check workflow bootstrap (the existing command runs
`python src/temporal/run_healthcheck_workflow.py`); append:

```
python src/temporal/run_retention_cleanup_schedule.py
```

so the schedule is (re)asserted on API startup, gated by `RETENTION_CLEANUP_ENABLED`.

- [ ] **Step 2: Validate compose syntax**

Run: `cd agentex && docker compose config >/dev/null && echo "compose ok"`
Expected: prints `compose ok` (no YAML/interpolation errors).

- [ ] **Step 3: Commit**

```bash
git add agentex/docker-compose.yml
git commit -m "feat(retention): wire cleanup worker + schedule bootstrap for local dev"
```

---

## Task 9: Full test sweep + final verification

- [ ] **Step 1: Run the full new test surface**

```bash
cd agentex
make test FILE=tests/unit/config/test_retention_cleanup_env.py
make test FILE=tests/unit/temporal/test_retention_cleanup_activities.py
make test FILE=tests/unit/temporal/test_retention_cleanup_workflow.py
make test FILE=tests/integration/test_retention_cleanup_discovery.py
```
Expected: all PASS.

- [ ] **Step 2: Lint the whole changed surface**

```bash
cd agentex && uv run ruff check src/ && uv run ruff format --check src/
```
Expected: no errors.

- [ ] **Step 3: Manual smoke (optional, local)**

With `RETENTION_CLEANUP_ENABLED=true` and `RETENTION_CLEANUP_AGENT_ALLOWLIST=<a-local-agent-name>`,
`make dev`, then in the Temporal UI (http://localhost:8080) confirm a Schedule
`retention-cleanup-sweep` exists; trigger it manually and confirm a
`RetentionCleanupSweepWorkflow` run completes with a summary.

- [ ] **Step 4: Final commit (if any lint/fixups remain)**

```bash
cd agentex && git add -A && git commit -m "chore(retention): lint + test fixups for scheduled cleanup" || echo "nothing to commit"
```

---

## Notes / Out of Scope

- **Worker must run in the deployed env.** This plan wires the worker for local
  docker-compose. The deployed (k8s) environment must run an agentex-backend
  Temporal worker on the `agentex-server` queue for the Schedule to execute —
  tracked as a separate infra change (see spec "Open prerequisites").
- **No export sink** in v1 (clean only), per the spec.
- **Audit trail** is the existing `task_cleanup_completed` structured log (emitted
  inside `clean_task`) plus the new `task_cleanup_skipped` and
  `retention_cleanup_sweep_completed` logs — faceted in Datadog. No new table.
