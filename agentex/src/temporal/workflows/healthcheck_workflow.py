"""
Temporal workflow for checking the status of an agent via its ACP endpoint.
"""

from datetime import timedelta

from src.temporal.activities.healthcheck_activities import (
    CHECK_STATUS_ACTIVITY,
    UPDATE_AGENT_STATUS_ACTIVITY,
)
from src.utils.logging import make_logger
from src.utils.observability import uses_observability_adapter
from temporalio import workflow
from temporalio.common import RetryPolicy

logger = workflow.logger if uses_observability_adapter() else make_logger(__name__)

FAILURE_THRESHOLD = 5
RECOVERY_THRESHOLD = 2


@workflow.defn
class HealthCheckWorkflow:
    """Continuously monitor an agent and persist health status transitions."""

    max_history_length: int = 10000

    @workflow.run
    async def run(self, workflow_args: dict) -> None:
        """
        Periodically check an agent's ACP endpoint.

        Five consecutive failed probes transition a ready agent to ``Unhealthy``.
        Two consecutive successful probes transition it back to ``Ready``. Workflow
        state is carried across continue-as-new runs so monitoring does not stop at
        either transition.

        Args:
            workflow_args: Dictionary containing ``agent_id``, ``acp_url``, and
                optional counters/status state carried across continue-as-new.
        """
        agent_id = workflow_args["agent_id"]
        acp_url = workflow_args["acp_url"]

        # Preserve command history for executions created by the first recovery fix.
        legacy_recover_on_next_success = workflow.patched(
            "recover-unhealthy-on-success"
        )
        continuous_recovery_enabled = workflow.patched(
            "continuous-health-state-recovery"
        )

        logger.info(f"Starting execution for agent {agent_id}")

        failure_counter = workflow_args.get("failure_counter", 0)
        recovery_counter = workflow_args.get("recovery_counter", 0)
        is_unhealthy = workflow_args.get(
            "is_unhealthy",
            workflow_args.get("initial_status") == "Unhealthy",
        )

        while not self.should_continue_as_new():
            await workflow.sleep(30)
            success = False
            try:
                success = await workflow.execute_activity(
                    CHECK_STATUS_ACTIVITY,
                    args=[agent_id, acp_url],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        initial_interval=timedelta(seconds=1),
                        backoff_coefficient=2.0,
                    ),
                )
            except Exception as e:
                detail = type(e).__name__ if uses_observability_adapter() else str(e)
                logger.error(f"Failed to check status of agent {agent_id}: {detail}")

            if not success:
                recovery_counter = 0
                failure_counter += 1
                if failure_counter >= FAILURE_THRESHOLD:
                    if not continuous_recovery_enabled or not is_unhealthy:
                        try:
                            result = await self._update_agent_status(
                                agent_id, "Unhealthy"
                            )
                        except Exception as e:
                            self._log_update_failure(agent_id, "Unhealthy", e)
                            continue
                        if result and not result["should_continue"]:
                            return
                        if result is None or result["changed"]:
                            self._log_transition(
                                agent_id=agent_id,
                                prior_status=(
                                    result["prior_status"] if result else "Ready"
                                ),
                                new_status="Unhealthy",
                                probe_result="unhealthy",
                                consecutive_count=failure_counter,
                            )
                    if not continuous_recovery_enabled:
                        # Preserve the behavior recorded by pre-fix workflow histories.
                        return
                    is_unhealthy = True
                    failure_counter = 0
                continue

            failure_counter = 0
            if not continuous_recovery_enabled:
                if legacy_recover_on_next_success:
                    try:
                        await self._update_agent_status(agent_id, "Ready")
                    except Exception as e:
                        self._log_update_failure(agent_id, "Ready", e)
                        continue
                    legacy_recover_on_next_success = False
                continue

            if is_unhealthy:
                recovery_counter += 1
                if recovery_counter >= RECOVERY_THRESHOLD:
                    try:
                        result = await self._update_agent_status(agent_id, "Ready")
                    except Exception as e:
                        self._log_update_failure(agent_id, "Ready", e)
                        continue
                    if result and not result["should_continue"]:
                        return
                    if result is None or result["changed"]:
                        self._log_transition(
                            agent_id=agent_id,
                            prior_status=(
                                result["prior_status"] if result else "Unhealthy"
                            ),
                            new_status="Ready",
                            probe_result="healthy",
                            consecutive_count=recovery_counter,
                        )
                    is_unhealthy = False
                    recovery_counter = 0
            else:
                recovery_counter = 0

        workflow_args.update(
            failure_counter=failure_counter,
            recovery_counter=recovery_counter,
            is_unhealthy=is_unhealthy,
        )
        workflow.continue_as_new(arg=workflow_args)

    async def _update_agent_status(
        self, agent_id: str, status: str
    ) -> dict[str, str | bool] | None:
        return await workflow.execute_activity(
            UPDATE_AGENT_STATUS_ACTIVITY,
            args=[agent_id, status],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
            ),
        )

    @staticmethod
    def _log_update_failure(agent_id: str, status: str, error: Exception) -> None:
        detail = type(error).__name__ if uses_observability_adapter() else str(error)
        logger.error(
            f"Failed to persist health status for agent {agent_id}: "
            f"target_status={status} error={detail}"
        )

    @staticmethod
    def _log_transition(
        *,
        agent_id: str,
        prior_status: str,
        new_status: str,
        probe_result: str,
        consecutive_count: int,
    ) -> None:
        logger.info(
            "Agent health status transition "
            f"agent_id={agent_id} prior_status={prior_status} "
            f"new_status={new_status} probe_result={probe_result} "
            f"consecutive_count={consecutive_count}"
        )

    def should_continue_as_new(self) -> bool:
        if workflow.info().is_continue_as_new_suggested():
            return True
        if (
            self.max_history_length
            and workflow.info().get_current_history_length() > self.max_history_length
        ):
            return True
        return False
