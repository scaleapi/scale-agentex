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
    monkeypatch.setenv("RETENTION_CLEANUP_DRY_RUN", "true")

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_ENABLED is True
    assert env.RETENTION_CLEANUP_AGENT_ALLOWLIST == ["agent-a", "agent-b", "agent-c"]
    assert env.RETENTION_CLEANUP_IDLE_DAYS == 14
    assert env.RETENTION_CLEANUP_CRON == "0 3 * * *"
    assert env.RETENTION_CLEANUP_PAGE_SIZE == 50
    assert env.RETENTION_CLEANUP_MAX_IN_FLIGHT == 5
    assert env.RETENTION_CLEANUP_DRY_RUN is True


@pytest.mark.unit
def test_retention_cleanup_env_defaults(monkeypatch):
    for key in (
        "RETENTION_CLEANUP_ENABLED",
        "RETENTION_CLEANUP_AGENT_ALLOWLIST",
        "RETENTION_CLEANUP_IDLE_DAYS",
        "RETENTION_CLEANUP_CRON",
        "RETENTION_CLEANUP_PAGE_SIZE",
        "RETENTION_CLEANUP_MAX_IN_FLIGHT",
        "RETENTION_CLEANUP_DRY_RUN",
    ):
        monkeypatch.delenv(key, raising=False)

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_ENABLED is False
    assert env.RETENTION_CLEANUP_AGENT_ALLOWLIST == []  # fail-closed
    assert env.RETENTION_CLEANUP_IDLE_DAYS == 7
    assert env.RETENTION_CLEANUP_CRON == "0 4 * * *"
    assert env.RETENTION_CLEANUP_PAGE_SIZE == 200
    assert env.RETENTION_CLEANUP_MAX_IN_FLIGHT == 20
    assert env.RETENTION_CLEANUP_DRY_RUN is True


@pytest.mark.unit
def test_retention_cleanup_env_allows_explicit_dry_run_false(monkeypatch):
    monkeypatch.setenv("RETENTION_CLEANUP_DRY_RUN", "false")

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_DRY_RUN is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("True", True),
        ("TRUE", True),
        ("1", True),
        (" true ", True),
        ("False", False),
        ("FALSE", False),
        ("0", False),
    ],
)
def test_retention_cleanup_bool_env_is_case_insensitive(monkeypatch, raw, expected):
    # YAML/Helm tooling tends to render booleans as True/False; the old strict
    # `== "true"` comparison silently turned DRY_RUN=True into live deletion.
    monkeypatch.setenv("RETENTION_CLEANUP_DRY_RUN", raw)

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_DRY_RUN is expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["yes", "on", "truee", "dry", ""])
def test_retention_cleanup_bool_env_rejects_garbage(monkeypatch, raw):
    monkeypatch.setenv("RETENTION_CLEANUP_DRY_RUN", raw)

    with pytest.raises(ValueError, match="RETENTION_CLEANUP_DRY_RUN"):
        EnvironmentVariables.refresh(force_refresh=True)


@pytest.mark.unit
def test_retention_cleanup_stale_running_days_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("RETENTION_CLEANUP_STALE_RUNNING_DAYS", raising=False)

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_STALE_RUNNING_DAYS == 0


@pytest.mark.unit
def test_retention_cleanup_stale_running_days_parses(monkeypatch):
    monkeypatch.setenv("RETENTION_CLEANUP_STALE_RUNNING_DAYS", "30")

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.RETENTION_CLEANUP_STALE_RUNNING_DAYS == 30
