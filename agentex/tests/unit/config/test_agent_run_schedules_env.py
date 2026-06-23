import pytest
from src.config.environment_variables import EnvironmentVariables


@pytest.mark.unit
def test_agent_run_schedules_flag_parses_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_AGENT_RUN_SCHEDULES", "true")

    env = EnvironmentVariables.refresh(force_refresh=True)

    assert env.ENABLE_AGENT_RUN_SCHEDULES is True


@pytest.mark.unit
def test_agent_run_schedules_flag_defaults_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_AGENT_RUN_SCHEDULES", raising=False)

    env = EnvironmentVariables.refresh(force_refresh=True)

    # Off by default — the API surface is absent unless an environment opts in.
    assert env.ENABLE_AGENT_RUN_SCHEDULES is False
