from types import SimpleNamespace
from typing import get_args
from unittest.mock import MagicMock

import pytest
from src.config import environment_variables as environment_variables_module
from src.config.environment_variables import EnvironmentVariables, StoragePhase
from src.domain.repositories import task_state_repository as selector_module
from src.domain.repositories.task_state_repository import (
    DTaskStateRepository,
    TaskStateRepository,
    TaskStateRepositoryProtocol,
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


def _force_cached_phase(monkeypatch, phase: StoragePhase):
    """Unimplemented phases are rejected by refresh() itself (the startup
    guard), so exercise the selector's own defense-in-depth branch by patching
    the cached config directly."""
    monkeypatch.delenv("TASK_STATE_STORAGE_PHASE", raising=False)
    env = EnvironmentVariables.refresh(force_refresh=True)
    monkeypatch.setattr(
        environment_variables_module,
        "refreshed_environment_variables",
        env.model_copy(update={"TASK_STATE_STORAGE_PHASE": phase}),
    )


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
    _force_cached_phase(monkeypatch, StoragePhase.POSTGRES)
    global_dependencies = MagicMock(
        side_effect=AssertionError("selector must not touch Mongo wiring")
    )
    monkeypatch.setattr(selector_module, "GlobalDependencies", global_dependencies)

    with pytest.raises(NotImplementedError, match="postgres"):
        get_task_state_repository()

    global_dependencies.assert_not_called()


@pytest.mark.unit
def test_mongo_repository_implements_every_protocol_method():
    """The Mongo repo explicitly subclasses the Protocol, so a missing method
    would silently inherit the protocol's `...` placeholder (returning None)
    instead of raising AttributeError. Pin that every required method is a
    real implementation."""
    for name in (
        "create",
        "batch_create",
        "get",
        "update",
        "delete",
        "list",
        "find_by_field",
        "delete_by_field",
        "get_by_task_and_agent",
    ):
        assert getattr(TaskStateRepository, name) is not getattr(
            TaskStateRepositoryProtocol, name
        ), f"{name} is still the protocol placeholder — not implemented"


@pytest.mark.unit
def test_di_seam_resolves_through_selector():
    """DTaskStateRepository is the seam every consumer (use case, authorization
    shortcuts, services) resolves; it must point at the phase selector."""
    depends_marker = get_args(DTaskStateRepository)[1]
    assert depends_marker.dependency is get_task_state_repository
