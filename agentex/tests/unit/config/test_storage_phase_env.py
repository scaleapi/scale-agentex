import pytest
from pydantic import ValidationError
from src.config.environment_variables import EnvironmentVariables, StoragePhase


@pytest.fixture(autouse=True)
def _reset_env_cache():
    """Drop the forced-refresh cache so later tests re-read a clean environment."""
    yield
    EnvironmentVariables.clear_cache()


@pytest.mark.unit
def test_storage_phases_default_to_mongodb(monkeypatch):
    monkeypatch.delenv("TASK_STATE_STORAGE_PHASE", raising=False)
    monkeypatch.delenv("TASK_MESSAGE_STORAGE_PHASE", raising=False)

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.TASK_STATE_STORAGE_PHASE == StoragePhase.MONGODB
    assert env.TASK_MESSAGE_STORAGE_PHASE == StoragePhase.MONGODB
    assert env.mongodb_required is True


@pytest.mark.unit
def test_storage_phases_parse_from_environment(monkeypatch):
    monkeypatch.setenv("TASK_STATE_STORAGE_PHASE", "mongodb")
    monkeypatch.setenv("TASK_MESSAGE_STORAGE_PHASE", "mongodb")

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.TASK_STATE_STORAGE_PHASE == StoragePhase.MONGODB
    assert env.TASK_MESSAGE_STORAGE_PHASE == StoragePhase.MONGODB


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw", ["mongo", "POSTGRES", "true", "", "dual_write", "dual_read"]
)
def test_storage_phase_rejects_unknown_values(monkeypatch, raw):
    # Fail loud on typos rather than silently falling back to a backend the
    # operator did not choose. dual_write/dual_read are deliberately not
    # defined: a data-migration effort would add its own phases.
    monkeypatch.setenv("TASK_STATE_STORAGE_PHASE", raw)

    with pytest.raises(ValidationError):
        EnvironmentVariables.refresh(force_refresh=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    "key", ["TASK_STATE_STORAGE_PHASE", "TASK_MESSAGE_STORAGE_PHASE"]
)
def test_unimplemented_phase_is_rejected_at_refresh(monkeypatch, key):
    """postgres is a valid phase value but has no repository yet: the config
    refresh (process startup, API and Temporal workers alike) must fail with
    the variable named — not the first state request or worker wiring."""
    monkeypatch.setenv(key, "postgres")

    with pytest.raises(ValueError, match=key):
        EnvironmentVariables.refresh(force_refresh=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("state_phase", "message_phase", "expected"),
    [
        ("mongodb", "mongodb", True),
        ("postgres", "mongodb", True),
        ("mongodb", "postgres", True),
        ("postgres", "postgres", False),
    ],
)
def test_mongodb_required_unless_every_phase_is_postgres(
    monkeypatch, state_phase, message_phase, expected
):
    monkeypatch.delenv("TASK_STATE_STORAGE_PHASE", raising=False)
    monkeypatch.delenv("TASK_MESSAGE_STORAGE_PHASE", raising=False)
    env = EnvironmentVariables.refresh(force_refresh=True)

    # Unimplemented phases cannot come from the environment (refresh rejects
    # them at startup), so pin the derived property on updated copies.
    patched = env.model_copy(
        update={
            "TASK_STATE_STORAGE_PHASE": StoragePhase(state_phase),
            "TASK_MESSAGE_STORAGE_PHASE": StoragePhase(message_phase),
        }
    )

    assert patched.mongodb_required is expected
