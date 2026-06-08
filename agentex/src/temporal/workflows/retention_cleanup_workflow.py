"""
Scheduled task-retention cleanup workflows.

RetentionCleanupSweepWorkflow: started by a Temporal Schedule. Pulls one page of
candidate task ids, fans out one child workflow per task (bounded by
max_in_flight), aggregates cleaned/skipped/failed counts, then continue_as_new's
to the next page so workflow history stays bounded regardless of backlog size.

RetentionCleanupTaskWorkflow: per-task child. Invokes the clean activity, which
already maps the policy/safety ClientError refusals to a 'skipped' outcome; only
genuine transient errors surface as activity failures (and are retried).
"""

import asyncio
from datetime import timedelta

from src.temporal.activities.retention_cleanup_activities import (
    CLEAN_TASK_ACTIVITY,
    FIND_CLEANUP_CANDIDATES_ACTIVITY,
    FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY,
    LOAD_CLEANUP_CONFIG_ACTIVITY,
)
from src.utils.logging import make_logger
from temporalio import workflow
from temporalio.common import RetryPolicy

logger = make_logger(__name__)


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


@workflow.defn
class RetentionCleanupTaskWorkflow:
    @workflow.run
    async def run(self, args: dict) -> dict:
        return await workflow.execute_activity(
            CLEAN_TASK_ACTIVITY,
            args=[args["task_id"], args["idle_days"], args.get("dry_run", False)],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )


@workflow.defn
class RetentionCleanupSweepWorkflow:
    @workflow.run
    async def run(self, args: dict | None = None) -> dict:
        args = args or {}

        # First page of a sweep: load policy from env (via activity) and carry it
        # across continue_as_new pages so a single sweep stays consistent even if
        # env changes mid-run. Subsequent pages already have it in args.
        if "idle_days" not in args:
            config = await workflow.execute_activity(
                LOAD_CLEANUP_CONFIG_ACTIVITY,
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=1),
                    backoff_coefficient=2.0,
                ),
            )
            args = {**args, **config}

        idle_days = args["idle_days"]
        agent_names = args["agent_names"]
        page_size = args.get("page_size", 200)
        max_in_flight = args.get("max_in_flight", 20)
        dry_run = args.get("dry_run", False)
        after_id = args.get("after_id")
        totals = args.get("totals", {"cleaned": 0, "skipped": 0, "failed": 0})

        if not args.get("enabled", True):
            logger.info("retention_cleanup_sweep_disabled", extra=totals)
            return totals

        task_ids = await workflow.execute_activity(
            FIND_CLEANUP_CANDIDATES_ACTIVITY,
            args=[after_id, page_size, idle_days, agent_names],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )

        if not task_ids:
            logger.info("retention_cleanup_sweep_completed", extra=totals)
            return totals

        page_last_id = task_ids[-1]
        multi_agent_task_ids = await workflow.execute_activity(
            FIND_MULTI_AGENT_CLEANUP_CANDIDATES_ACTIVITY,
            args=[task_ids],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )
        if multi_agent_task_ids:
            multi_agent_task_id_set = set(multi_agent_task_ids)
            totals["skipped"] = totals.get("skipped", 0) + len(multi_agent_task_ids)
            totals["skipped_multi_agent"] = totals.get("skipped_multi_agent", 0) + len(
                multi_agent_task_ids
            )
            logger.warning(
                "retention_cleanup_multi_agent_candidates_skipped",
                extra={"task_ids": multi_agent_task_ids},
            )
            task_ids = [
                task_id
                for task_id in task_ids
                if task_id not in multi_agent_task_id_set
            ]

        # Scope child workflow IDs to this run so a task re-discovered in a later
        # sweep (e.g. one that was skipped) doesn't collide with a prior cycle's
        # completed child under a REJECT_DUPLICATE workflow-id-reuse policy.
        sweep_run_id = workflow.info().run_id[:8]
        for batch in _chunked(task_ids, max_in_flight):
            results = await asyncio.gather(
                *[
                    workflow.execute_child_workflow(
                        RetentionCleanupTaskWorkflow.run,
                        {
                            "task_id": task_id,
                            "idle_days": idle_days,
                            "dry_run": dry_run,
                        },
                        id=f"retention-cleanup-task-{sweep_run_id}-{task_id}",
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    for task_id in batch
                ],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    totals["failed"] += 1
                else:
                    status = result.get("status", "failed")
                    totals[status] = totals.get(status, 0) + 1

        workflow.continue_as_new(
            arg={
                "enabled": args.get("enabled", True),
                "idle_days": idle_days,
                "agent_names": agent_names,
                "page_size": page_size,
                "max_in_flight": max_in_flight,
                "dry_run": dry_run,
                "after_id": page_last_id,
                "totals": totals,
            }
        )
