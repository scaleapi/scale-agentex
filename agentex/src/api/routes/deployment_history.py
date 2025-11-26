from fastapi import APIRouter, HTTPException, status

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.deployment_history import (
    DeploymentHistory,
)
from src.domain.use_cases.agents_use_case import DAgentsUseCase
from src.domain.use_cases.deployment_history_use_case import DDeploymentHistoryUseCase
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/deployment-history", tags=["Deployment History"])


@router.get(
    "/{deployment_id}",
    summary="Get Deployment by ID",
    response_model=DeploymentHistory,
    description="Get a deployment record by its unique ID.",
)
async def get_deployment_by_id(
    deployment_id: str,
    deployment_history_use_case: DDeploymentHistoryUseCase,
) -> DeploymentHistory:
    """Get a deployment record by its unique ID."""
    try:
        deployment_entity = await deployment_history_use_case.get_deployment(
            deployment_id=deployment_id
        )
    except ItemDoesNotExist as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment not found: {e}",
        ) from e
    return DeploymentHistory.model_validate(deployment_entity)


@router.get(
    "",
    summary="List Deployments for an agent",
    response_model=list[DeploymentHistory],
    description="List deployment history for an agent.",
)
async def list_deployments(
    deployment_history_use_case: DDeploymentHistoryUseCase,
    agent_use_case: DAgentsUseCase,
    agent_id: str | None = None,
    agent_name: str | None = None,
    limit: int = 50,
    page_number: int = 1,
    order_by: str | None = None,
    order_direction: str = "desc",
) -> list[DeploymentHistory]:
    """List deployment history"""
    if not agent_id and not agent_name:
        raise HTTPException(
            status_code=400,
            detail="Either 'agent_id' or 'agent_name' must be provided to list deployment history.",
        )
    if agent_id and agent_name:
        raise HTTPException(
            status_code=400,
            detail="Only one of 'agent_id' or 'agent_name' should be provided to list deployment history.",
        )
    agent = await agent_use_case.get(id=agent_id, name=agent_name)
    deployments = await deployment_history_use_case.list_deployments(
        agent_id=agent.id,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
    )

    # Convert entities to API schemas
    return [DeploymentHistory.model_validate(d) for d in deployments]
