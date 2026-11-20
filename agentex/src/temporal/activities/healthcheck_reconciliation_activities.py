"""Activities for recurring health-check workflow reconciliation."""

from src.temporal.healthcheck_reconciliation import reconcile_healthcheck_workflows
from temporalio import activity

RECONCILE_HEALTHCHECK_WORKFLOWS_ACTIVITY = "reconcile_healthcheck_workflows_activity"


class HealthCheckReconciliationActivities:
    def __init__(self, agent_repo, temporal_adapter, task_queue: str):
        self.agent_repo = agent_repo
        self.temporal_adapter = temporal_adapter
        self.task_queue = task_queue

    @activity.defn(name=RECONCILE_HEALTHCHECK_WORKFLOWS_ACTIVITY)
    async def reconcile(self) -> dict[str, int]:
        return await reconcile_healthcheck_workflows(
            self.agent_repo,
            self.temporal_adapter,
            self.task_queue,
        )
