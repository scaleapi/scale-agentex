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
async def test_find_multi_agent_cleanup_candidates_delegates_to_repo():
    repo = AsyncMock()
    repo.list_multi_agent_task_ids.return_value = ["t2"]
    activities = RetentionCleanupActivities(task_repository=repo, use_case=AsyncMock())

    result = await activities.find_multi_agent_cleanup_candidates(["t1", "t2"])

    assert result == ["t2"]
    repo.list_multi_agent_task_ids.assert_awaited_once_with(task_ids=["t1", "t2"])


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
    activities = RetentionCleanupActivities(
        task_repository=AsyncMock(), use_case=use_case
    )

    outcome = await activities.clean_task(task_id="t1", idle_days=7, dry_run=False)

    assert outcome["status"] == "cleaned"
    assert outcome["task_id"] == "t1"
    assert outcome["messages_deleted"] == 3
    use_case.clean_task.assert_awaited_once_with(task_id="t1", force=False, idle_days=7)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_defaults_to_dry_run_and_validates_without_writes():
    use_case = AsyncMock()
    use_case.preview_clean_task.return_value = TaskCleanupResultEntity(
        task_id="t1",
        cleaned_at=datetime.now(UTC),
        messages_deleted=0,
        task_states_deleted=0,
        events_deleted=0,
    )
    activities = RetentionCleanupActivities(
        task_repository=AsyncMock(), use_case=use_case
    )

    outcome = await activities.clean_task(task_id="t1", idle_days=7)

    assert outcome["status"] == "dry_run"
    assert outcome["task_id"] == "t1"
    assert outcome["reason"] == "would_clean"
    use_case.preview_clean_task.assert_awaited_once_with(
        task_id="t1", force=False, idle_days=7
    )
    use_case.clean_task.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_clienterror_maps_to_skipped():
    use_case = AsyncMock()
    use_case.clean_task.side_effect = ClientError(
        "Cannot clean task t1: status is RUNNING (active)"
    )
    activities = RetentionCleanupActivities(
        task_repository=AsyncMock(), use_case=use_case
    )

    outcome = await activities.clean_task(task_id="t1", idle_days=7, dry_run=False)

    assert outcome["status"] == "skipped"
    assert "RUNNING" in outcome["reason"]
    assert outcome["task_id"] == "t1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_unexpected_error_propagates():
    use_case = AsyncMock()
    use_case.clean_task.side_effect = RuntimeError("mongo timeout")
    activities = RetentionCleanupActivities(
        task_repository=AsyncMock(), use_case=use_case
    )

    with pytest.raises(RuntimeError):
        await activities.clean_task(task_id="t1", idle_days=7, dry_run=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_cleanup_config_reads_env(monkeypatch):
    monkeypatch.setenv("RETENTION_CLEANUP_ENABLED", "true")
    monkeypatch.setenv("RETENTION_CLEANUP_AGENT_ALLOWLIST", "x,y")
    monkeypatch.setenv("RETENTION_CLEANUP_IDLE_DAYS", "9")
    monkeypatch.setenv("RETENTION_CLEANUP_PAGE_SIZE", "33")
    monkeypatch.setenv("RETENTION_CLEANUP_MAX_IN_FLIGHT", "4")
    monkeypatch.setenv("RETENTION_CLEANUP_DRY_RUN", "true")
    activities = RetentionCleanupActivities(
        task_repository=AsyncMock(), use_case=AsyncMock()
    )
    config = await activities.load_cleanup_config()
    assert config == {
        "enabled": True,
        "idle_days": 9,
        "agent_names": ["x", "y"],
        "page_size": 33,
        "max_in_flight": 4,
        "dry_run": True,
    }
