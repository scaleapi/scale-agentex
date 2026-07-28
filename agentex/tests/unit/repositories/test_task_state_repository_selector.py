from types import SimpleNamespace
from typing import get_args
from unittest.mock import MagicMock

import pytest
from src.config.environment_variables import EnvironmentVariables
from src.domain.repositories import task_state_repository as selector_module
from src.domain.repositories.task_state_repository import (
    DTaskStateRepository,
    TaskStateRepository,
    get_task_state_repository,
)


@pytest.fixture(autouse=True)
def _reset_env_cache():
    """Drop the forced-refresh cache so later tests re-read a clean environment."""
    yield
    EnvironmentVariables.clear_cache()


def _set_phase(monkeypatch, phase: str | None):
    if phase is None:
        monkeypatch.delenv("TASK_STATE_STORAGE_PHASE", raising=False)
    else:
        monkeypatch.setenv("TASK_STATE_STORAGE_PHASE", phase)
    EnvironmentVariables.refresh(force_refresh=True)


@pytest.mark.unit
@pytest.mark.parametrize("phase", [None, "mongodb"])
def test_selector_returns_mongo_repository_for_mongodb_phase(monkeypatch, phase):
    _set_phase(monkeypatch, phase)
    mongo_db = MagicMock()
    monkeypatch.setattr(
        selector_module,
        "GlobalDependencies",
        lambda: SimpleNamespace(mongodb_database=mongo_db),
    )

    repository = get_task_state_repository()

    assert isinstance(repository, TaskStateRepository)
    assert repository.db is mongo_db


@pytest.mark.unit
def test_selector_rejects_unimplemented_phases_lazily(monkeypatch):
    """Unimplemented phases fail loud, and without touching any Mongo wiring:
    the mongodb branch must be the only one that needs a Mongo handle."""
    phase = "postgres"
    _set_phase(monkeypatch, phase)
    global_dependencies = MagicMock(
        side_effect=AssertionError("selector must not touch Mongo wiring")
    )
    monkeypatch.setattr(selector_module, "GlobalDependencies", global_dependencies)

    with pytest.raises(NotImplementedError, match=phase):
        get_task_state_repository()

    global_dependencies.assert_not_called()


@pytest.mark.unit
def test_di_seam_resolves_through_selector():
    """DTaskStateRepository is the seam every consumer (use case, authorization
    shortcuts, services) resolves; it must point at the phase selector."""
    depends_marker = get_args(DTaskStateRepository)[1]
    assert depends_marker.dependency is get_task_state_repository
