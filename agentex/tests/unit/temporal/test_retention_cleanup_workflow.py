import uuid

import pytest
from src.temporal.activities.retention_cleanup_activities import (
    CLEAN_TASK_ACTIVITY,
    FIND_CLEANUP_CANDIDATES_ACTIVITY,
    FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY,
    LOAD_CLEANUP_CONFIG_ACTIVITY,
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

    @activity.defn(name=FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find_multi_agent(task_ids: list[str]) -> list[str]:
        return []

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int, dry_run: bool) -> dict:
        assert dry_run is False
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
            activities=[fake_find, fake_find_multi_agent, fake_clean],
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sweep_loads_config_from_activity_when_no_args():
    pages = {None: ["t1"], "t1": []}

    @activity.defn(name=LOAD_CLEANUP_CONFIG_ACTIVITY)
    async def fake_load() -> dict:
        return {
            "idle_days": 7,
            "agent_names": ["a"],
            "page_size": 2,
            "max_in_flight": 2,
        }

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find(after_id, limit, idle_days, agent_names) -> list[str]:
        assert agent_names == ["a"]  # policy from load activity flowed through
        return pages[after_id]

    @activity.defn(name=FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find_multi_agent(task_ids: list[str]) -> list[str]:
        return []

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int, dry_run: bool) -> dict:
        assert dry_run is False
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
            task_queue="test-retention-load",
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[fake_load, fake_find, fake_find_multi_agent, fake_clean],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            summary = await env.client.execute_workflow(
                RetentionCleanupSweepWorkflow.run,
                id=f"sweep-{uuid.uuid4()}",
                task_queue="test-retention-load",
            )
    assert summary["cleaned"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sweep_noops_when_runtime_config_disabled():
    @activity.defn(name=LOAD_CLEANUP_CONFIG_ACTIVITY)
    async def fake_load() -> dict:
        return {
            "enabled": False,
            "idle_days": 7,
            "agent_names": ["a"],
            "page_size": 2,
            "max_in_flight": 2,
        }

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find(after_id, limit, idle_days, agent_names) -> list[str]:
        raise AssertionError("disabled cleanup should not discover candidates")

    @activity.defn(name=FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find_multi_agent(task_ids: list[str]) -> list[str]:
        raise AssertionError("disabled cleanup should not check multi-agent candidates")

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int, dry_run: bool) -> dict:
        raise AssertionError("disabled cleanup should not clean tasks")

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-retention-disabled",
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[fake_load, fake_find_multi_agent, fake_find, fake_clean],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            summary = await env.client.execute_workflow(
                RetentionCleanupSweepWorkflow.run,
                id=f"sweep-{uuid.uuid4()}",
                task_queue="test-retention-disabled",
            )

    assert summary == {"cleaned": 0, "skipped": 0, "failed": 0}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sweep_skips_multi_agent_candidates_before_cleanup():
    pages = {None: ["t1", "t2", "t3"], "t3": []}
    cleaned_task_ids = []

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find(after_id, limit, idle_days, agent_names) -> list[str]:
        return pages[after_id]

    @activity.defn(name=FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find_multi_agent(task_ids: list[str]) -> list[str]:
        assert task_ids == ["t1", "t2", "t3"]
        return ["t2"]

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int, dry_run: bool) -> dict:
        cleaned_task_ids.append(task_id)
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
            task_queue="test-retention-multi-agent",
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[fake_find, fake_find_multi_agent, fake_clean],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            summary = await env.client.execute_workflow(
                RetentionCleanupSweepWorkflow.run,
                {
                    "idle_days": 7,
                    "agent_names": ["a"],
                    "page_size": 3,
                    "max_in_flight": 2,
                },
                id=f"sweep-{uuid.uuid4()}",
                task_queue="test-retention-multi-agent",
            )

    assert set(cleaned_task_ids) == {"t1", "t3"}
    assert "t2" not in cleaned_task_ids
    assert summary["cleaned"] == 2
    assert summary["skipped"] == 1
    assert summary["skipped_multi_agent"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sweep_propagates_dry_run_to_child_cleanup():
    pages = {None: ["t1"], "t1": []}

    @activity.defn(name=LOAD_CLEANUP_CONFIG_ACTIVITY)
    async def fake_load() -> dict:
        return {
            "enabled": True,
            "dry_run": True,
            "idle_days": 7,
            "agent_names": ["a"],
            "page_size": 2,
            "max_in_flight": 2,
        }

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find(after_id, limit, idle_days, agent_names) -> list[str]:
        return pages[after_id]

    @activity.defn(name=FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY)
    async def fake_find_multi_agent(task_ids: list[str]) -> list[str]:
        return []

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def fake_clean(task_id: str, idle_days: int, dry_run: bool) -> dict:
        assert dry_run is True
        return {
            "task_id": task_id,
            "status": "dry_run",
            "reason": "would_clean",
            "messages_deleted": 0,
            "task_states_deleted": 0,
            "events_deleted": 0,
        }

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-retention-dry-run",
            workflows=[RetentionCleanupSweepWorkflow, RetentionCleanupTaskWorkflow],
            activities=[fake_load, fake_find, fake_find_multi_agent, fake_clean],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            summary = await env.client.execute_workflow(
                RetentionCleanupSweepWorkflow.run,
                id=f"sweep-{uuid.uuid4()}",
                task_queue="test-retention-dry-run",
            )

    assert summary["dry_run"] == 1
    assert summary["cleaned"] == 0
