import uuid

import pytest
from src.temporal.activities.retention_cleanup_activities import (
    CLEAN_TASK_ACTIVITY,
    FIND_CLEANUP_CANDIDATES_ACTIVITY,
)
from src.temporal.workflows.retention_cleanup_workflow import (
    RetentionCleanupSweepWorkflow,
    RetentionCleanupTaskWorkflow,
)
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sweep_cleans_all_pages_and_aggregates():
    pages = {None: ["t1", "t2"], "t2": ["t3"], "t3": []}

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find(after_id, limit, idle_days, agent_names) -> list[str]:
        return pages[after_id]

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int) -> dict:
        if task_id == "t2":
            return {
                "task_id": task_id,
                "status": "skipped",
                "reason": "RUNNING",
                "messages_deleted": 0,
                "task_states_deleted": 0,
                "events_deleted": 0,
            }
        if task_id == "t3":
            raise RuntimeError("permanent failure")
        return {
            "task_id": task_id,
            "status": "cleaned",
            "reason": None,
            "messages_deleted": 1,
            "task_states_deleted": 0,
            "events_deleted": 0,
        }

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-retention",
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[fake_find, fake_clean],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            summary = await env.client.execute_workflow(
                RetentionCleanupSweepWorkflow.run,
                {
                    "idle_days": 7,
                    "agent_names": ["a"],
                    "page_size": 2,
                    "max_in_flight": 2,
                },
                id=f"sweep-{uuid.uuid4()}",
                task_queue="test-retention",
            )

    assert summary["cleaned"] == 1  # t1
    assert summary["skipped"] == 1  # t2
    assert summary["failed"] == 1  # t3
