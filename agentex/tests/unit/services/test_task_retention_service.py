from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.domain.entities.tasks import TaskStatus
from src.domain.services.task_retention_service import TaskRetentionService


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
