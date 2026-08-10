"""The Temporal factories build repositories by hand, outside FastAPI's Depends
DI. These tests pin that both factories resolve the task-state repository
through the shared phase selector instead of constructing the Mongo repository
directly — otherwise a Postgres deployment's workers would silently keep
writing task state to MongoDB."""

from unittest.mock import MagicMock

import pytest
from src.temporal import scheduled_agent_run_factory, task_retention_factory


@pytest.mark.unit
def test_retention_factory_resolves_state_repo_through_selector(monkeypatch):
    sentinel_repository = MagicMock()
    selector = MagicMock(return_value=sentinel_repository)
    monkeypatch.setattr(task_retention_factory, "get_task_state_repository", selector)

    use_case = task_retention_factory.build_task_retention_use_case(MagicMock())

    selector.assert_called_once_with()
    assert use_case.retention_service.task_state_repository is sentinel_repository


@pytest.mark.unit
def test_scheduled_run_factory_resolves_state_repo_through_selector(monkeypatch):
    sentinel_repository = MagicMock()
    selector = MagicMock(return_value=sentinel_repository)
    monkeypatch.setattr(
        scheduled_agent_run_factory, "get_task_state_repository", selector
    )

    use_case = scheduled_agent_run_factory.build_acp_use_case_for_principal(
        MagicMock(), {"user_id": "u1", "account_id": "a1"}
    )

    selector.assert_called_once_with()
    assert use_case.task_service.task_state_repository is sentinel_repository
