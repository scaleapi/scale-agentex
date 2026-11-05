"""Shared reconciliation logic for per-agent health-check workflows."""

from temporalio.common import WorkflowIDReusePolicy

from src.adapters.temporal.exceptions import TemporalWorkflowAlreadyExistsError
from src.domain.entities.agents import AgentStatus
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow
from src.utils.logging import make_logger

logger = make_logger(__name__)

MONITORED_AGENT_PAGE_SIZE = 200
MONITORED_AGENT_STATUSES = (AgentStatus.READY, AgentStatus.UNHEALTHY)


async def reconcile_healthcheck_workflows(
    agent_repo, temporal_adapter, task_queue: str
):
    """Ensure every ready or unhealthy registered agent has a health monitor."""
    totals = {"started": 0, "already_running": 0, "skipped": 0, "failed": 0}
    for status in MONITORED_AGENT_STATUSES:
        page_number = 1
        while True:
            agents = await agent_repo.list(
                filters={"status": status},
                limit=MONITORED_AGENT_PAGE_SIZE,
                page_number=page_number,
                order_by="id",
                order_direction="asc",
            )
            if not agents:
                break

            for agent in agents:
                if not agent.acp_url:
                    totals["skipped"] += 1
                    logger.warning(
                        f"Skipping health check workflow for agent {agent.id}: "
                        "ACP URL is not configured"
                    )
                    continue
                try:
                    await temporal_adapter.start_workflow(
                        workflow_id=f"healthcheck_workflow_{agent.id}",
                        workflow=HealthCheckWorkflow,
                        args=[
                            {
                                "agent_id": agent.id,
                                "acp_url": agent.acp_url,
                                "initial_status": agent.status.value,
                            }
                        ],
                        task_queue=task_queue,
                        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                    )
                    totals["started"] += 1
                except TemporalWorkflowAlreadyExistsError:
                    totals["already_running"] += 1
                    logger.info(
                        f"Health check workflow already exists for agent {agent.id}"
                    )
                except Exception as e:
                    totals["failed"] += 1
                    logger.error(
                        f"Failed to start health check workflow for agent {agent.id}: {e}"
                    )

            if len(agents) < MONITORED_AGENT_PAGE_SIZE:
                break
            page_number += 1
    return totals
