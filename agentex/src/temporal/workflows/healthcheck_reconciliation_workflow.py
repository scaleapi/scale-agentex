"""Scheduled workflow that restores missing per-agent health monitors."""

from datetime import timedelta

from src.temporal.activities.healthcheck_reconciliation_activities import (
    RECONCILE_HEALTHCHECK_WORKFLOWS_ACTIVITY,
)
from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class HealthCheckReconciliationWorkflow:
    @workflow.run
    async def run(self) -> dict[str, int]:
        return await workflow.execute_activity(
            RECONCILE_HEALTHCHECK_WORKFLOWS_ACTIVITY,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )
