"""
Scheduled agent run workflow (AGX1-368).

Started by a Temporal Schedule on each cron / interval fire. The workflow is
deliberately thin: it passes only the schedule id and a per-fire token to a
single activity and does no DB / API / ACP work itself, so it stays
deterministic. All side effects live in ``launch_scheduled_agent_run``.

The per-fire token is the workflow id, which Temporal makes unique per scheduled
fire (it suffixes the configured workflow id with the nominal fire time) and
keeps stable across activity retries within the same execution. The activity
uses it to build a deterministic, idempotent task name.
"""

from datetime import timedelta
from typing import Any

from src.temporal.activities.scheduled_agent_run_activities import (
    LAUNCH_SCHEDULED_AGENT_RUN_ACTIVITY,
)
from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class ScheduledAgentRunWorkflow:
    @workflow.run
    async def run(self, schedule_id: str) -> dict[str, Any]:
        fire_id = workflow.info().workflow_id
        return await workflow.execute_activity(
            LAUNCH_SCHEDULED_AGENT_RUN_ACTIVITY,
            args=[schedule_id, fire_id],
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=2),
                backoff_coefficient=2.0,
            ),
        )
