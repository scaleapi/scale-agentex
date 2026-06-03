"""
Temporal activities for the scheduled task-retention cleanup sweep.

Three activities:
- load_cleanup_config: reads RETENTION_CLEANUP_* env vars at run time so policy
  changes take effect on the next scheduled run without recreating the schedule.
- find_cleanup_candidates: cheap pre-filtered, keyset-paginated discovery.
- clean_task: delegates to TaskRetentionUseCase.clean_task; catches ClientError
  (the three policy/safety refusals) and maps it to a 'skipped' outcome so the
  caller's child workflow completes cleanly. Genuine transient errors propagate
  so Temporal retries them.

Boundary types are JSON-native (the backend data converter does not serialize
Pydantic models).
"""

from typing import TypedDict

from src.config.environment_variables import EnvironmentVariables
from src.domain.exceptions import ClientError
from src.domain.repositories.task_repository import TaskRepository
from src.domain.use_cases.task_retention_use_case import TaskRetentionUseCase
from src.utils.logging import make_logger
from temporalio import activity

logger = make_logger(__name__)

LOAD_CLEANUP_CONFIG_ACTIVITY = "load_cleanup_config_activity"
FIND_CLEANUP_CANDIDATES_ACTIVITY = "find_cleanup_candidates_activity"
CLEAN_TASK_ACTIVITY = "clean_task_activity"


class CleanTaskOutcome(TypedDict):
    task_id: str
    status: str  # "cleaned" | "skipped"
    reason: str | None
    messages_deleted: int
    task_states_deleted: int
    events_deleted: int


class RetentionCleanupActivities:
    def __init__(
        self,
        task_repository: TaskRepository,
        use_case: TaskRetentionUseCase,
    ):
        self.task_repository = task_repository
        self.use_case = use_case

    @activity.defn(name=LOAD_CLEANUP_CONFIG_ACTIVITY)
    async def load_cleanup_config(self) -> dict:
        """
        Read the current retention-cleanup policy from the environment.

        Policy (allowlist, idle threshold, paging) is intentionally NOT baked into
        the Temporal Schedule. The sweep loads it here at run time so changing a
        RETENTION_CLEANUP_* env var and restarting the worker takes effect on the
        next scheduled run without recreating the schedule.
        """
        # Lives on this class (rather than as a free function) only so the worker
        # can register it alongside the other activities; it intentionally uses
        # none of the injected repositories/use case.
        env = EnvironmentVariables.refresh(force_refresh=True)
        return {
            "idle_days": env.RETENTION_CLEANUP_IDLE_DAYS,
            "agent_names": env.RETENTION_CLEANUP_AGENT_ALLOWLIST,
            "page_size": env.RETENTION_CLEANUP_PAGE_SIZE,
            "max_in_flight": env.RETENTION_CLEANUP_MAX_IN_FLIGHT,
        }

    @activity.defn(name=FIND_CLEANUP_CANDIDATES_ACTIVITY)
    async def find_cleanup_candidates(
        self,
        after_id: str | None,
        limit: int,
        idle_days: int,
        agent_names: list[str],
    ) -> list[str]:
        """
        Return a page of task IDs that are eligible for content cleanup.

        Args:
            after_id: Keyset cursor — return only IDs strictly after this value,
                or None to start from the beginning.
            limit: Maximum number of IDs to return.
            idle_days: Minimum number of days a task must have been idle to qualify.
            agent_names: Restrict candidates to tasks belonging to these agents.

        Returns:
            list[str]: Up to *limit* task IDs ordered by ID, suitable for passing
                back as *after_id* on the next page.
        """
        logger.info(
            "find_cleanup_candidates_started",
            extra={"after_id": after_id, "limit": limit},
        )
        result = await self.task_repository.list_cleanup_candidate_ids(
            idle_days=idle_days,
            agent_names=agent_names,
            after_id=after_id,
            limit=limit,
        )
        logger.info("find_cleanup_candidates_completed", extra={"count": len(result)})
        return result

    @activity.defn(name=CLEAN_TASK_ACTIVITY)
    async def clean_task(self, task_id: str, idle_days: int) -> CleanTaskOutcome:
        """
        Delete the stored content (messages, states, events) for a single task.

        Args:
            task_id: ID of the task to clean.
            idle_days: Passed through to the use case for policy checks.

        Returns:
            CleanTaskOutcome with ``status`` set to ``"cleaned"`` when content was
            deleted, or ``"skipped"`` when the use case refused via ``ClientError``
            (e.g. task is still active, not yet idle long enough, or already
            cleaned).  Other exceptions propagate so Temporal can retry them.
        """
        try:
            result = await self.use_case.clean_task(
                task_id=task_id, force=False, idle_days=idle_days
            )
            return {
                "task_id": result.task_id,
                "status": "cleaned",
                "reason": None,
                "messages_deleted": result.messages_deleted,
                "task_states_deleted": result.task_states_deleted,
                "events_deleted": result.events_deleted,
            }
        except ClientError as e:
            logger.info(
                "task_cleanup_skipped",
                extra={"task_id": task_id, "reason": str(e)},
            )
            return {
                "task_id": task_id,
                "status": "skipped",
                "reason": str(e),
                "messages_deleted": 0,
                "task_states_deleted": 0,
                "events_deleted": 0,
            }
