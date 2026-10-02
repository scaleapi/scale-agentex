from unittest.mock import Mock

import pytest
from src.temporal.activities.healthcheck_activities import (
    CHECK_STATUS_ACTIVITY,
    UPDATE_AGENT_STATUS_ACTIVITY,
)
from src.temporal.workflows import healthcheck_workflow
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow


async def _run_workflow(
    monkeypatch,
    probe_results,
    workflow_args,
    *,
    continuous=True,
    update_failures=0,
):
    results = iter(probe_results)
    remaining_update_failures = update_failures
    persisted_status = workflow_args.get("initial_status", "Ready")
    status_updates = []
    trace = []

    async def execute_activity(activity_name, *, args, **kwargs):
        nonlocal persisted_status, remaining_update_failures
        if activity_name == CHECK_STATUS_ACTIVITY:
            result = next(results)
            trace.append(["probe", result])
            return result
        if activity_name == UPDATE_AGENT_STATUS_ACTIVITY:
            if remaining_update_failures:
                remaining_update_failures -= 1
                raise RuntimeError("database unavailable")
            status_updates.append(args)
            trace.append(["update", args[1]])
            prior_status = persisted_status
            persisted_status = args[1]
            return {
                "changed": prior_status != persisted_status,
                "prior_status": prior_status,
                "current_status": persisted_status,
                "should_continue": True,
            }
        raise AssertionError(f"Unexpected activity: {activity_name}")

    async def sleep(_):
        return None

    workflow_instance = HealthCheckWorkflow()
    workflow_instance.should_continue_as_new = Mock(
        side_effect=([False] * len(probe_results)) + [True]
    )
    continue_as_new = Mock()
    logger = Mock()
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
    monkeypatch.setattr(healthcheck_workflow, "logger", logger)

    def patched(patch_id):
        if patch_id == "recover-unhealthy-on-success":
            return True
        if patch_id == "continuous-health-state-recovery":
            return continuous
        raise AssertionError(f"Unexpected patch ID: {patch_id}")

    monkeypatch.setattr(healthcheck_workflow.workflow, "patched", patched)

    await workflow_instance.run(workflow_args)
    return status_updates, trace, continue_as_new, logger


@pytest.mark.asyncio
@pytest.mark.unit
async def test_unhealthy_agent_recovers_after_two_successful_probes(monkeypatch):
    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Unhealthy",
    }

    status_updates, trace, continue_as_new, logger = await _run_workflow(
        monkeypatch,
        [True, True, True],
        workflow_args,
    )

    assert status_updates == [["agent-1", "Ready"]]
    assert trace == [
        ["probe", True],
        ["probe", True],
        ["update", "Ready"],
        ["probe", True],
    ]
    assert workflow_args == {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Unhealthy",
        "failure_counter": 0,
        "recovery_counter": 0,
        "is_unhealthy": False,
    }
    continue_as_new.assert_called_once_with(arg=workflow_args)
    assert "prior_status=Unhealthy" in logger.info.call_args_list[-1].args[0]
    assert "new_status=Ready" in logger.info.call_args_list[-1].args[0]
    assert "probe_result=healthy" in logger.info.call_args_list[-1].args[0]
    assert "consecutive_count=2" in logger.info.call_args_list[-1].args[0]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_five_failures_mark_unhealthy_without_stopping_monitor(monkeypatch):
    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Ready",
    }

    status_updates, trace, continue_as_new, logger = await _run_workflow(
        monkeypatch,
        [False, False, False, False, False, False],
        workflow_args,
    )

    assert status_updates == [["agent-1", "Unhealthy"]]
    assert sum(item[0] == "probe" for item in trace) == 6
    assert workflow_args["is_unhealthy"] is True
    assert workflow_args["failure_counter"] == 1
    continue_as_new.assert_called_once_with(arg=workflow_args)
    transition_log = logger.info.call_args_list[-1].args[0]
    assert "prior_status=Ready" in transition_log
    assert "new_status=Unhealthy" in transition_log
    assert "probe_result=unhealthy" in transition_log
    assert "consecutive_count=5" in transition_log


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ready_agent_completes_full_unhealthy_recovery_cycle(monkeypatch):
    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Ready",
    }

    status_updates, _, continue_as_new, _ = await _run_workflow(
        monkeypatch,
        [False, False, False, False, False, True, True],
        workflow_args,
    )

    assert status_updates == [
        ["agent-1", "Unhealthy"],
        ["agent-1", "Ready"],
    ]
    assert workflow_args["is_unhealthy"] is False
    assert workflow_args["failure_counter"] == 0
    assert workflow_args["recovery_counter"] == 0
    continue_as_new.assert_called_once_with(arg=workflow_args)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_success_resets_failure_streak(monkeypatch):
    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Ready",
    }

    status_updates, _, _, _ = await _run_workflow(
        monkeypatch,
        [False, False, True, False, False, False, False, False],
        workflow_args,
    )

    assert status_updates == [["agent-1", "Unhealthy"]]
    assert workflow_args["is_unhealthy"] is True
    assert workflow_args["failure_counter"] == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_failed_probe_resets_recovery_streak(monkeypatch):
    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Unhealthy",
    }

    status_updates, _, _, _ = await _run_workflow(
        monkeypatch,
        [True, False, True, True],
        workflow_args,
    )

    assert status_updates == [["agent-1", "Ready"]]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_status_update_failure_does_not_stop_monitoring(monkeypatch):
    workflow_args = {
        "agent_id": "agent-1",
        "acp_url": "http://agent",
        "initial_status": "Ready",
    }

    status_updates, trace, continue_as_new, logger = await _run_workflow(
        monkeypatch,
        [False, False, False, False, False, False],
        workflow_args,
        update_failures=1,
    )

    assert status_updates == [["agent-1", "Unhealthy"]]
    assert sum(item[0] == "probe" for item in trace) == 6
    continue_as_new.assert_called_once_with(arg=workflow_args)
    assert any(
        "target_status=Unhealthy" in call.args[0]
        for call in logger.error.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pre_fix_history_retains_stop_after_unhealthy_transition(monkeypatch):
    workflow_args = {"agent_id": "agent-1", "acp_url": "http://agent"}

    status_updates, _, continue_as_new, _ = await _run_workflow(
        monkeypatch,
        [False, False, False, False, False],
        workflow_args,
        continuous=False,
    )

    assert status_updates == [["agent-1", "Unhealthy"]]
    continue_as_new.assert_not_called()
