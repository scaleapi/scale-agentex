from unittest.mock import AsyncMock

import pytest
from src.temporal.activities.healthcheck_reconciliation_activities import (
    RECONCILE_HEALTHCHECK_WORKFLOWS_ACTIVITY,
)
from src.temporal.workflows import healthcheck_reconciliation_workflow
from src.temporal.workflows.healthcheck_reconciliation_workflow import (
    HealthCheckReconciliationWorkflow,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_reconciliation_workflow_runs_sweep_activity(monkeypatch):
    execute_activity = AsyncMock(
        return_value={"started": 1, "already_running": 2, "skipped": 0, "failed": 0}
    )
    monkeypatch.setattr(
        healthcheck_reconciliation_workflow.workflow,
        "execute_activity",
        execute_activity,
    )

    result = await HealthCheckReconciliationWorkflow().run()

    assert result == {
        "started": 1,
        "already_running": 2,
        "skipped": 0,
        "failed": 0,
    }
    assert execute_activity.await_args.args == (
        RECONCILE_HEALTHCHECK_WORKFLOWS_ACTIVITY,
    )
