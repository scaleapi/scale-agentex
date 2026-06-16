from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.domain.entities.tasks import TaskStatus
from src.domain.exceptions import ClientError
from src.domain.services.task_retention_service import TaskRetentionService


def _make_service(task, *, messages=None):
    task_repository = AsyncMock()
    task_repository.get.return_value = task
    task_message_service = AsyncMock()
    task_message_service.get_messages.return_value = messages or []
    task_message_service.delete_all_messages.return_value = 0
    task_state_repository = AsyncMock()
    task_state_repository.delete_by_field.return_value = 0
    event_repository = AsyncMock()
    event_repository.delete_by_task_id.return_value = 0
    agent_task_tracker_repository = AsyncMock()
    agent_task_tracker_repository.find_by_field.return_value = []

    return TaskRetentionService(
        task_repository=task_repository,
        task_message_service=task_message_service,
        task_message_repository=AsyncMock(),
        task_state_repository=task_state_repository,
        event_repository=event_repository,
        agent_task_tracker_repository=agent_task_tracker_repository,
        temporal_adapter=AsyncMock(),
        httpx_client=AsyncMock(),
    )


def _running_task(idle_for_days: int):
    return SimpleNamespace(
        id="t1",
        cleaned_at=None,
        status=TaskStatus.RUNNING,
        updated_at=datetime.now(UTC) - timedelta(days=idle_for_days),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_clean_task_validates_without_writes():
    task_repository = AsyncMock()
    task_repository.get.return_value = SimpleNamespace(
        id="t1",
        cleaned_at=None,
        status=TaskStatus.COMPLETED,
        updated_at=datetime.now(UTC) - timedelta(days=30),
    )
    task_message_service = AsyncMock()
    task_message_service.get_messages.return_value = []
    task_message_repository = AsyncMock()
    task_state_repository = AsyncMock()
    event_repository = AsyncMock()
    agent_task_tracker_repository = AsyncMock()
    agent_task_tracker_repository.find_by_field.return_value = []

    service = TaskRetentionService(
        task_repository=task_repository,
        task_message_service=task_message_service,
        task_message_repository=task_message_repository,
        task_state_repository=task_state_repository,
        event_repository=event_repository,
        agent_task_tracker_repository=agent_task_tracker_repository,
        temporal_adapter=AsyncMock(),
        httpx_client=AsyncMock(),
    )

    result = await service.preview_clean_task(task_id="t1", idle_days=7)

    assert result.task_id == "t1"
    assert result.messages_deleted == 0
    assert result.task_states_deleted == 0
    assert result.events_deleted == 0
    task_message_service.delete_all_messages.assert_not_awaited()
    task_state_repository.delete_by_field.assert_not_awaited()
    event_repository.delete_by_task_id.assert_not_awaited()
    agent_task_tracker_repository.reset_cursors_for_task.assert_not_awaited()
    task_repository.update.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_refuses_running_task_by_default():
    service = _make_service(_running_task(idle_for_days=90))

    with pytest.raises(ClientError, match="RUNNING"):
        await service.clean_task(task_id="t1", idle_days=7)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_cleans_stale_running_task_with_override():
    service = _make_service(_running_task(idle_for_days=90))

    result = await service.clean_task(task_id="t1", idle_days=7, stale_running_days=30)

    assert result.task_id == "t1"
    service.task_message_service.delete_all_messages.assert_awaited_once_with("t1")
    service.task_repository.update.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_refuses_running_task_not_stale_enough():
    # RUNNING and idle 10 days: past idle_days (7) but short of the
    # stale-RUNNING threshold (30) — must still be refused.
    service = _make_service(_running_task(idle_for_days=10))

    with pytest.raises(ClientError, match="RUNNING"):
        await service.clean_task(task_id="t1", idle_days=7, stale_running_days=30)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_running_override_respects_recent_messages():
    # Postgres row is stale but a recent Mongo message proves interaction:
    # last-interaction = max(updated_at, latest message), so no override.
    recent_message = SimpleNamespace(created_at=datetime.now(UTC) - timedelta(days=1))
    service = _make_service(_running_task(idle_for_days=90), messages=[recent_message])

    with pytest.raises(ClientError, match="RUNNING"):
        await service.clean_task(task_id="t1", idle_days=7, stale_running_days=30)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_clean_task_applies_stale_running_override():
    service = _make_service(_running_task(idle_for_days=90))

    result = await service.preview_clean_task(
        task_id="t1", idle_days=7, stale_running_days=30
    )

    assert result.task_id == "t1"
    service.task_message_service.delete_all_messages.assert_not_awaited()
    service.task_repository.update.assert_not_awaited()


def _completed_task(idle_for_days: int):
    return SimpleNamespace(
        id="t1",
        cleaned_at=None,
        status=TaskStatus.COMPLETED,
        updated_at=datetime.now(UTC) - timedelta(days=idle_for_days),
    )


def _wire_unprocessed_events(service):
    # One tracker with a stalled (NULL) cursor and an event past it: the
    # shape signal-driven agents (e.g. One Edge) leave behind, since they
    # never advance the agent_task_tracker cursor.
    service.agent_task_tracker_repository.find_by_field.return_value = [
        SimpleNamespace(agent_id="a1", last_processed_event_id=None)
    ]
    service.event_repository.list_events_after_last_processed.return_value = [
        SimpleNamespace(id="e1")
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_refuses_unprocessed_events_by_default():
    # Idle, terminal task (passes running + idle guards) but with events past
    # the cursor and no stale override: must still refuse.
    service = _make_service(_completed_task(idle_for_days=90))
    _wire_unprocessed_events(service)

    with pytest.raises(ClientError, match="unprocessed events"):
        await service.clean_task(task_id="t1", idle_days=7)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_cleans_stale_idle_task_with_unprocessed_events():
    # RUNNING + idle 90d + trailing unprocessed events: with the stale
    # override both guards relax and the task is cleaned (the One Edge case).
    service = _make_service(_running_task(idle_for_days=90))
    _wire_unprocessed_events(service)

    result = await service.clean_task(task_id="t1", idle_days=7, stale_running_days=30)

    assert result.task_id == "t1"
    service.task_message_service.delete_all_messages.assert_awaited_once_with("t1")
    service.task_repository.update.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clean_task_unprocessed_events_not_relaxed_when_not_stale_enough():
    # RUNNING + idle 10d, stale threshold 30d: not abandoned yet, so the
    # RUNNING guard fires first (and unprocessed would too). Must refuse.
    service = _make_service(_running_task(idle_for_days=10))
    _wire_unprocessed_events(service)

    with pytest.raises(ClientError):
        await service.clean_task(task_id="t1", idle_days=7, stale_running_days=30)
