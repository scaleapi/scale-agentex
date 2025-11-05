"""
Temporal workflow for checking the status of an agent via its ACP endpoint.
"""

from datetime import timedelta

from src.temporal.activities.healthcheck_activities import (
    CHECK_STATUS_ACTIVITY,
    UPDATE_AGENT_STATUS_ACTIVITY,
)
from src.utils.logging import make_logger
from temporalio import workflow
from temporalio.common import RetryPolicy

logger = make_logger(__name__)


@workflow.defn
class HealthCheckWorkflow:
    """
        Workflow for checking the status of an agent via its ACP endpoint.

    This workflow:
    1. Checks the status of an agent via its ACP endpoint
    2. Updates the agent status in the database
    3. If the agent is not healthy, it stops the workflow
    """

    max_history_length: int = 10000

    @workflow.run
    async def run(self, workflow_args: dict) -> None:
        """
        Periodically checks the health of an agent via its ACP endpoint and updates its status in the database.
        If the agent fails health checks repeatedly, marks the agent as failed and stops further checks.

        Args:
            workflow_args: Dictionary containing:
                - agent_id: Database agent ID to check
                - acp_url: Registered agent ACP URL

        Returns:
            None
        """
        # Extract arguments
        agent_id = workflow_args["agent_id"]
        acp_url = workflow_args["acp_url"]

        logger.info(f"Starting execution for agent {agent_id}")

        failure_counter = workflow_args.get("failure_counter", 0)
        while not self.should_continue_as_new():
            # Wait for the next health check
            await workflow.sleep(30)
            try:
                # Call the Activity with a retry policy
                await workflow.execute_activity(
                    CHECK_STATUS_ACTIVITY,
                    args=[agent_id, acp_url],
                    start_to_close_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        initial_interval=timedelta(seconds=1),
                        backoff_coefficient=2.0,
                    ),
                )
            except Exception:
                # Activity failed after all retries
                failure_counter += 1
                if failure_counter >= 5:
                    # Agent is officially unhealthy
                    await workflow.execute_activity(
                        UPDATE_AGENT_STATUS_ACTIVITY,
                        args=[agent_id, "Unhealthy"],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(
                            maximum_attempts=3,
                            initial_interval=timedelta(seconds=1),
                            backoff_coefficient=2.0,
                        ),
                    )
                    # Stop health check workflow until agent registers again
                    return
                else:
                    continue

            # If health check succeeds, reset the counter
            failure_counter = 0

        workflow_args["failure_counter"] = failure_counter
        workflow.continue_as_new(
            arg=workflow_args,
        )

    def should_continue_as_new(self) -> bool:
        if workflow.info().is_continue_as_new_suggested():
            return True
        # For testing
        if (
            self.max_history_length
            and workflow.info().get_current_history_length() > self.max_history_length
        ):
            return True
        return False
