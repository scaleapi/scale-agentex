from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends
from temporalio.common import WorkflowIDReusePolicy

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.temporal.adapter_temporal import DTemporalAdapter
from src.adapters.temporal.exceptions import (
    TemporalWorkflowAlreadyExistsError,
    TemporalWorkflowNotFoundError,
)
from src.config.environment_variables import EnvironmentVariables
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.domain.exceptions import ClientError
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.repositories.deployment_repository import DDeploymentRepository
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class DeploymentUseCase:
    def __init__(
        self,
        deployment_repository: DDeploymentRepository,
        agent_repository: DAgentRepository,
        temporal_adapter: DTemporalAdapter,
    ):
        self.deployment_repo = deployment_repository
        self.agent_repo = agent_repository
        self.temporal_adapter = temporal_adapter

    async def restart_healthcheck_workflow_for_deployment(
        self,
        deployment: DeploymentEntity,
    ) -> None:
        environment_variables = EnvironmentVariables.refresh()
        if not environment_variables.ENABLE_HEALTH_CHECK_WORKFLOW:
            logger.info(
                "Health check workflow is not enabled for promoted deployment %s",
                deployment.id,
            )
            return
        if not deployment.acp_url:
            logger.warning(
                "Promoted deployment %s has no acp_url; skipping health check workflow",
                deployment.id,
            )
            return

        workflow_id = f"healthcheck_workflow_{deployment.agent_id}"
        try:
            await self.temporal_adapter.terminate_workflow(
                workflow_id=workflow_id,
                reason=(
                    "Restarting health check workflow for promoted deployment "
                    f"{deployment.id}"
                ),
            )
        except TemporalWorkflowNotFoundError:
            logger.info("No existing health check workflow to restart: %s", workflow_id)
        except Exception as e:
            error_detail = getattr(e, "detail", None)
            error_text = f"{e} {error_detail or ''}".lower()
            if "already completed" in error_text:
                logger.info(
                    "Existing health check workflow already completed: %s",
                    workflow_id,
                )
            else:
                logger.error(
                    "Failed to terminate existing health check workflow %s: %s",
                    workflow_id,
                    e,
                )
                return

        try:
            await self.temporal_adapter.start_workflow(
                workflow_id=workflow_id,
                workflow=HealthCheckWorkflow,
                args=[{"agent_id": deployment.agent_id, "acp_url": deployment.acp_url}],
                task_queue=environment_variables.AGENTEX_SERVER_TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            )
            logger.info(
                "Started health check workflow %s for promoted deployment %s",
                workflow_id,
                deployment.id,
            )
        except TemporalWorkflowAlreadyExistsError:
            logger.info("Health check workflow already exists: %s", workflow_id)
        except Exception as e:
            logger.error(
                "Failed to start health check workflow %s for promoted deployment %s: %s",
                workflow_id,
                deployment.id,
                e,
            )

    async def create_deployment(
        self,
        agent_id: str,
        docker_image: str,
        registration_metadata: dict[str, Any] | None = None,
        sgp_deploy_id: str | None = None,
        helm_release_name: str | None = None,
    ) -> DeploymentEntity:
        # Validate agent exists
        await self.agent_repo.get(id=agent_id)

        deployment = DeploymentEntity(
            id=orm_id(),
            agent_id=agent_id,
            docker_image=docker_image,
            registration_metadata=registration_metadata,
            status=DeploymentStatus.PENDING,
            is_production=False,
            sgp_deploy_id=sgp_deploy_id,
            helm_release_name=helm_release_name,
        )
        return await self.deployment_repo.create(deployment)

    async def get_deployment(
        self, agent_id: str, deployment_id: str
    ) -> DeploymentEntity:
        deployment = await self.deployment_repo.get(id=deployment_id)
        if deployment.agent_id != agent_id:
            raise ItemDoesNotExist(
                f"Deployment {deployment_id} not found for agent {agent_id}"
            )
        return deployment

    async def list_deployments(
        self,
        agent_id: str,
        limit: int = 50,
        page_number: int = 1,
        order_by: str | None = None,
        order_direction: str = "desc",
    ) -> list[DeploymentEntity]:
        return await self.deployment_repo.list_for_agent(
            agent_id=agent_id,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )

    async def promote_deployment(
        self,
        agent_id: str,
        deployment_id: str,
    ) -> DeploymentEntity:
        logger.info(f"Promoting deployment {deployment_id} for agent {agent_id}")
        deployment = await self.deployment_repo.promote(
            agent_id=agent_id,
            deployment_id=deployment_id,
        )
        await self.restart_healthcheck_workflow_for_deployment(deployment)
        return deployment

    async def delete_deployment(
        self,
        agent_id: str,
        deployment_id: str,
    ) -> DeploymentEntity:
        deployment = await self.deployment_repo.get(id=deployment_id)
        if deployment.agent_id != agent_id:
            raise ItemDoesNotExist(
                f"Deployment {deployment_id} not found for agent {agent_id}"
            )
        if deployment.is_production:
            raise ClientError(
                "Cannot delete the current production deployment. "
                "Promote a different deployment first."
            )
        deployment.expires_at = datetime.now(UTC)
        return await self.deployment_repo.update(deployment)


DDeploymentUseCase = Annotated[DeploymentUseCase, Depends(DeploymentUseCase)]
