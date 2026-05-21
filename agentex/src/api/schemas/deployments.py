from datetime import datetime
from typing import Any

from pydantic import Field

from src.domain.entities.deployments import DeploymentStatus
from src.utils.model_utils import BaseModel


class Deployment(BaseModel):
    id: str = Field(..., description="The unique identifier of the deployment.")
    agent_id: str = Field(..., description="The agent this deployment belongs to.")
    docker_image: str = Field(..., description="Full Docker image URI.")
    registration_metadata: dict[str, Any] | None = Field(
        None, description="Git/build metadata from the agent pod."
    )
    status: DeploymentStatus = Field(..., description="Current deployment status.")
    acp_url: str | None = Field(None, description="ACP URL set when agent registers.")
    is_production: bool = Field(
        ..., description="Whether this is the production deployment."
    )
    sgp_deploy_id: str | None = Field(
        None, description="Correlates to SGP's agentex_deploys.id."
    )
    helm_release_name: str | None = Field(
        None, description="Helm release name for cleanup."
    )
    created_at: datetime | None = Field(
        None, description="When the deployment was created."
    )
    promoted_at: datetime | None = Field(
        None, description="When promoted to production."
    )
    expires_at: datetime | None = Field(None, description="When marked for cleanup.")

    class Config:
        orm_mode = True


class CreateDeploymentRequest(BaseModel):
    docker_image: str = Field(..., description="Full Docker image URI.")
    registration_metadata: dict[str, Any] | None = Field(
        None,
        description="Git/build metadata (commit_hash, branch_name, author_name, author_email, build_timestamp).",
    )
    sgp_deploy_id: str | None = Field(None, description="SGP deployment ID.")
    helm_release_name: str | None = Field(None, description="Helm release name.")
