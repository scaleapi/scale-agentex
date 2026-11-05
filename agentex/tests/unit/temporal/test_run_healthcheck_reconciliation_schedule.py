from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.adapters.temporal.exceptions import TemporalScheduleAlreadyExistsError
from src.temporal import run_healthcheck_reconciliation_schedule as schedule_runner
from src.temporal.workflows.healthcheck_reconciliation_workflow import (
    HealthCheckReconciliationWorkflow,
)


async def _run(monkeypatch, *, enabled=True, configured=True, schedule_error=None):
    dependencies = SimpleNamespace(temporal_client=object(), load=AsyncMock())
    adapter = SimpleNamespace(create_schedule=AsyncMock(side_effect=schedule_error))
    env = SimpleNamespace(
        ENABLE_HEALTH_CHECK_WORKFLOW=enabled,
        AGENTEX_SERVER_TASK_QUEUE="agentex-server",
    )
    monkeypatch.setattr(schedule_runner, "GlobalDependencies", lambda: dependencies)
    monkeypatch.setattr(schedule_runner.EnvironmentVariables, "refresh", lambda: env)
    monkeypatch.setattr(
        schedule_runner.TemporalClientFactory,
        "is_temporal_configured",
        lambda _: configured,
    )
    monkeypatch.setattr(schedule_runner, "TemporalAdapter", lambda **_: adapter)

    await schedule_runner.main()
    return adapter


@pytest.mark.asyncio
@pytest.mark.unit
async def test_schedule_is_created_idempotently_with_skip_overlap(monkeypatch):
    adapter = await _run(monkeypatch)

    adapter.create_schedule.assert_awaited_once_with(
        schedule_id=schedule_runner.SCHEDULE_ID,
        workflow=HealthCheckReconciliationWorkflow.run,
        workflow_id=schedule_runner.WORKFLOW_ID,
        args=[],
        task_queue="agentex-server",
        interval_seconds=schedule_runner.RECONCILIATION_INTERVAL_SECONDS,
        overlap_policy="skip",
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_existing_schedule_is_left_unchanged(monkeypatch):
    error = TemporalScheduleAlreadyExistsError(
        message="already exists",
        detail="already exists",
    )

    adapter = await _run(monkeypatch, schedule_error=error)

    adapter.create_schedule.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("enabled", "configured"),
    [(False, True), (True, False)],
)
async def test_schedule_is_skipped_when_healthchecks_cannot_run(
    monkeypatch, enabled, configured
):
    adapter = await _run(monkeypatch, enabled=enabled, configured=configured)

    adapter.create_schedule.assert_not_awaited()
