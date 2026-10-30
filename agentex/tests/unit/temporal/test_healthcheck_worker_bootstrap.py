from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.temporal import run_worker


@pytest.mark.asyncio
@pytest.mark.unit
async def test_worker_bootstrap_installs_schedule_and_reconciles(monkeypatch):
    adapter = object()
    ensure_schedule = AsyncMock()
    reconcile = AsyncMock(return_value={"started": 1})
    monkeypatch.setattr(
        run_worker.EnvironmentVariables,
        "refresh",
        lambda: SimpleNamespace(ENABLE_HEALTH_CHECK_WORKFLOW=True),
    )
    monkeypatch.setattr(
        run_worker.TemporalClientFactory,
        "is_temporal_configured",
        lambda _: True,
    )
    monkeypatch.setattr(run_worker, "TemporalAdapter", lambda _: adapter)
    monkeypatch.setattr(run_worker, "ensure_reconciliation_schedule", ensure_schedule)
    monkeypatch.setattr(run_worker, "reconcile_healthcheck_workflows", reconcile)
    repo = object()
    dependencies = SimpleNamespace(temporal_client=object())

    await run_worker.bootstrap_healthcheck_reconciliation(
        repo,
        dependencies,
        "agentex-server",
    )

    ensure_schedule.assert_awaited_once_with(adapter, "agentex-server")
    reconcile.assert_awaited_once_with(repo, adapter, "agentex-server")


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("enabled", "configured"),
    [(False, True), (True, False)],
)
async def test_worker_bootstrap_is_skipped_when_healthchecks_cannot_run(
    monkeypatch, enabled, configured
):
    ensure_schedule = AsyncMock()
    monkeypatch.setattr(
        run_worker.EnvironmentVariables,
        "refresh",
        lambda: SimpleNamespace(ENABLE_HEALTH_CHECK_WORKFLOW=enabled),
    )
    monkeypatch.setattr(
        run_worker.TemporalClientFactory,
        "is_temporal_configured",
        lambda _: configured,
    )
    monkeypatch.setattr(run_worker, "ensure_reconciliation_schedule", ensure_schedule)

    await run_worker.bootstrap_healthcheck_reconciliation(
        object(),
        SimpleNamespace(temporal_client=object()),
        "agentex-server",
    )

    ensure_schedule.assert_not_awaited()
