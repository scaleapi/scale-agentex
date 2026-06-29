"""Unit tests for the MongoDB OIDC client-refresh path in GlobalDependencies.

pymongo's built-in GCP OIDC provider caches the access token for the life of the
client and never refreshes it proactively, so a long-lived client fails auth once
the ~1h GCP token expires. `refresh_mongodb_client()` rebuilds the client to renew
the token without bouncing the process; these tests cover the gating, the
build-validate-swap-drain ordering, and the loop lifecycle — all without a real
MongoDB (the client is mocked).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.config.dependencies import GlobalDependencies, Singleton
from src.config.environment_variables import EnvironmentVariables

OIDC_URI = (
    "mongodb://host/?authMechanism=MONGODB-OIDC"
    "&authMechanismProperties=ENVIRONMENT:gcp,TOKEN_RESOURCE:FIRESTORE"
)
PLAIN_URI = "mongodb://user:pass@host:27017/?authSource=admin"


@pytest.fixture
def deps():
    """A fresh GlobalDependencies, isolated from the process-wide singleton."""
    Singleton._instances.pop(GlobalDependencies, None)
    instance = GlobalDependencies()
    yield instance
    Singleton._instances.pop(GlobalDependencies, None)


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.admin.command = AsyncMock(return_value={"ok": 1})
    client.close = AsyncMock()
    return client


def _set_uri(deps: GlobalDependencies, uri: str | None) -> None:
    deps.environment_variables = deps.environment_variables.model_copy(
        update={"MONGODB_URI": uri, "MONGODB_DATABASE_NAME": "agentex"}
    )


@pytest.mark.unit
def test_env_refresh_interval_parses_and_defaults(monkeypatch):
    monkeypatch.setenv("MONGODB_OIDC_REFRESH_INTERVAL_SECONDS", "900")
    assert (
        EnvironmentVariables.refresh(
            force_refresh=True
        ).MONGODB_OIDC_REFRESH_INTERVAL_SECONDS
        == 900
    )

    monkeypatch.delenv("MONGODB_OIDC_REFRESH_INTERVAL_SECONDS", raising=False)
    assert (
        EnvironmentVariables.refresh(
            force_refresh=True
        ).MONGODB_OIDC_REFRESH_INTERVAL_SECONDS
        == 2700
    )


@pytest.mark.unit
def test_uses_oidc_gate(deps):
    _set_uri(deps, OIDC_URI)
    assert deps._mongodb_uses_oidc() is True

    _set_uri(deps, PLAIN_URI)
    assert deps._mongodb_uses_oidc() is False

    _set_uri(deps, None)
    assert deps._mongodb_uses_oidc() is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_swaps_client_and_drains_old(deps, monkeypatch):
    _set_uri(deps, OIDC_URI)
    old_client = _mock_client()
    new_client = _mock_client()
    deps.mongodb_client = old_client
    monkeypatch.setattr(deps, "_build_mongodb_client", lambda uri: new_client)

    await deps.refresh_mongodb_client()

    # New client validated before the swap, then installed.
    new_client.admin.command.assert_awaited_once_with("ping")
    assert deps.mongodb_client is new_client
    assert deps.mongodb_database is new_client["agentex"]

    # Old client is scheduled for a drained close, not closed immediately.
    old_client.close.assert_not_awaited()
    assert len(deps._mongodb_close_tasks) == 1
    for task in list(deps._mongodb_close_tasks):
        task.cancel()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_noop_for_non_oidc(deps, monkeypatch):
    _set_uri(deps, PLAIN_URI)
    old_client = _mock_client()
    deps.mongodb_client = old_client
    build = MagicMock()
    monkeypatch.setattr(deps, "_build_mongodb_client", build)

    await deps.refresh_mongodb_client()

    build.assert_not_called()
    assert deps.mongodb_client is old_client


@pytest.mark.asyncio
@pytest.mark.unit
async def test_refresh_keeps_old_client_when_new_fails_validation(deps, monkeypatch):
    _set_uri(deps, OIDC_URI)
    old_client = _mock_client()
    deps.mongodb_client = old_client

    broken = _mock_client()
    broken.admin.command = AsyncMock(side_effect=RuntimeError("auth failed"))
    monkeypatch.setattr(deps, "_build_mongodb_client", lambda uri: broken)

    with pytest.raises(RuntimeError):
        await deps.refresh_mongodb_client()

    # Never swapped to the broken client; never tore down the working one.
    assert deps.mongodb_client is old_client
    old_client.close.assert_not_awaited()
    # The candidate is closed before re-raising, so repeated failures can't leak
    # orphaned clients across retries.
    broken.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_loop_start_gating(deps):
    deps.mongodb_client = _mock_client()

    # Disabled by interval.
    _set_uri(deps, OIDC_URI)
    deps.environment_variables = deps.environment_variables.model_copy(
        update={"MONGODB_OIDC_REFRESH_INTERVAL_SECONDS": 0}
    )
    deps._start_mongodb_oidc_refresh_loop()
    assert deps._mongodb_refresh_task is None

    # Disabled by non-OIDC URI.
    _set_uri(deps, PLAIN_URI)
    deps.environment_variables = deps.environment_variables.model_copy(
        update={"MONGODB_OIDC_REFRESH_INTERVAL_SECONDS": 2700}
    )
    deps._start_mongodb_oidc_refresh_loop()
    assert deps._mongodb_refresh_task is None

    # Enabled: OIDC + positive interval.
    _set_uri(deps, OIDC_URI)
    deps.environment_variables = deps.environment_variables.model_copy(
        update={"MONGODB_OIDC_REFRESH_INTERVAL_SECONDS": 2700}
    )
    deps._start_mongodb_oidc_refresh_loop()
    assert deps._mongodb_refresh_task is not None

    await deps._stop_mongodb_oidc_refresh_loop()
    assert deps._mongodb_refresh_task is None
