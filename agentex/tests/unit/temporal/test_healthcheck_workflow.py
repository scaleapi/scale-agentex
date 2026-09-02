from unittest.mock import Mock

import pytest
from src.temporal.activities.healthcheck_activities import (
    CHECK_STATUS_ACTIVITY,
    UPDATE_AGENT_STATUS_ACTIVITY,
)
from src.temporal.workflows import healthcheck_workflow
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("patch_enabled", "starting_failure_counter", "expected_status_updates"),
    [
        (True, 0, [["agent-1", "Ready"]]),
        (True, 2, [["agent-1", "Ready"]]),
        (False, 0, []),
    ],
)
async def test_first_healthy_probe_recovers_new_workflows_once(
    monkeypatch,
    patch_enabled,
    starting_failure_counter,
    expected_status_updates,
):
    status_updates = []
    trace = []
    patch_ids = []
    probe_results = iter([True, True])

    async def execute_activity(activity_name, *, args, **kwargs):
        if activity_name == CHECK_STATUS_ACTIVITY:
            result = next(probe_results)
            trace.append(["probe", result])
            return result
        if activity_name == UPDATE_AGENT_STATUS_ACTIVITY:
            status_updates.append(args)
            trace.append(["update", *args[1:]])
            return None
        raise AssertionError(f"Unexpected activity: {activity_name}")

    async def sleep(_):
        return None

    workflow_instance = HealthCheckWorkflow()
    workflow_instance.should_continue_as_new = Mock(side_effect=[False, False, True])
    continue_as_new = Mock()
    monkeypatch.setattr(healthcheck_workflow.workflow, "sleep", sleep)
    monkeypatch.setattr(
        healthcheck_workflow.workflow,
        "execute_activity",
        execute_activity,
    )
    monkeypatch.setattr(
        healthcheck_workflow.workflow,
        "continue_as_new",
        continue_as_new,
    )

    def patched(patch_id):
        patch_ids.append(patch_id)
        return patch_enabled

    monkeypatch.setattr(healthcheck_workflow.workflow, "patched", patched)

    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "failure_counter": starting_failure_counter,
    }
    await workflow_instance.run(workflow_args)

    assert patch_ids == ["recover-unhealthy-on-success"]
    assert status_updates == expected_status_updates
    expected_trace = [["probe", True]]
    if expected_status_updates:
        expected_trace.append(["update", "Ready"])
    expected_trace.append(["probe", True])
    assert trace == expected_trace
    assert workflow_args["failure_counter"] == 0
    continue_as_new.assert_called_once_with(arg=workflow_args)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_five_failed_probes_mark_unhealthy_and_stop(monkeypatch):
    status_updates = []
    probe_count = 0

    async def execute_activity(activity_name, *, args, **kwargs):
        nonlocal probe_count
        if activity_name == CHECK_STATUS_ACTIVITY:
            probe_count += 1
            return False
        if activity_name == UPDATE_AGENT_STATUS_ACTIVITY:
            status_updates.append(args)
            return None
        raise AssertionError(f"Unexpected activity: {activity_name}")

    async def sleep(_):
        return None

    workflow_instance = HealthCheckWorkflow()
    workflow_instance.should_continue_as_new = Mock(
        side_effect=[False, False, False, False, False, True]
    )
    continue_as_new = Mock()
    monkeypatch.setattr(healthcheck_workflow.workflow, "sleep", sleep)
    monkeypatch.setattr(
        healthcheck_workflow.workflow,
        "execute_activity",
        execute_activity,
    )
    monkeypatch.setattr(
        healthcheck_workflow.workflow,
        "continue_as_new",
        continue_as_new,
    )
    monkeypatch.setattr(
        healthcheck_workflow.workflow,
        "patched",
        lambda _: True,
    )

    await workflow_instance.run({"agent_id": "agent-1", "acp_url": "http://agent"})

    assert status_updates == [
        ["agent-1", "Unhealthy"]
    ], "the fifth consecutive failed probe must mark the agent unhealthy"
    assert probe_count == 5, "the workflow must wait for five failed probes"
    continue_as_new.assert_not_called()
