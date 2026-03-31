from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.domain.exceptions import ClientError
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.repositories.deployment_repository import DDeploymentRepository
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class DeploymentUseCase:
    def __init__(
        self,
        deployment_repository: DDeploymentRepository,
        agent_repository: DAgentRepository,
    ):
        self.deployment_repo = deployment_repository
        self.agent_repo = agent_repository

    async def create_deployment(
        self,
        agent_id: str,
        docker_image: str,
        commit_hash: str | None = None,
        branch_name: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
        sgp_deploy_id: str | None = None,
        helm_release_name: str | None = None,
        build_timestamp: datetime | None = None,
    ) -> DeploymentEntity:
        # Validate agent exists
        await self.agent_repo.get(id=agent_id)

        deployment = DeploymentEntity(
            id=orm_id(),
            agent_id=agent_id,
            docker_image=docker_image,
            commit_hash=commit_hash,
            branch_name=branch_name,
            author_name=author_name,
            author_email=author_email,
            build_timestamp=build_timestamp,
            status=DeploymentStatus.PENDING,
            is_production=False,
            sgp_deploy_id=sgp_deploy_id,
            helm_release_name=helm_release_name,
        )
        return await self.deployment_repo.create(deployment)

    async def get_deployment(self, deployment_id: str) -> DeploymentEntity:
        return await self.deployment_repo.get(id=deployment_id)

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
        return await self.deployment_repo.promote(
            agent_id=agent_id,
            deployment_id=deployment_id,
        )

    async def rollback_deployment(
        self,
        agent_id: str,
        deployment_id: str,
    ) -> DeploymentEntity:
        logger.info(f"Rolling back to deployment {deployment_id} for agent {agent_id}")
        return await self.deployment_repo.promote(
            agent_id=agent_id,
            deployment_id=deployment_id,
        )

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
