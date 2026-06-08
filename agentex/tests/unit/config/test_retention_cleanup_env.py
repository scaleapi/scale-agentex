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
    assert env.RETENTION_CLEANUP_DRY_RUN is False
