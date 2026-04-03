from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.utils.model_utils import BaseModel


class DeploymentStatus(str, Enum):
    PENDING = "Pending"
    READY = "Ready"
    FAILED = "Failed"


class DeploymentEntity(BaseModel):
    id: str = Field(..., description="The unique identifier of the deployment.")
    agent_id: str = Field(..., description="The agent this deployment belongs to.")

    # Image (immutable after creation)
    docker_image: str = Field(..., description="Full Docker image URI.")

    # Git/build metadata (commit_hash, branch_name, author_name, author_email, build_timestamp)
    registration_metadata: dict[str, Any] | None = Field(
        None, description="Registration metadata from the agent pod."
    )

    # Runtime state
    status: DeploymentStatus = Field(
        DeploymentStatus.PENDING,
        description="Current deployment status.",
    )
    acp_url: str | None = Field(None, description="ACP URL set when agent registers.")
    is_production: bool = Field(
        False, description="Whether this is the production deployment."
    )

    # Infra references
    sgp_deploy_id: str | None = Field(
        None, description="Correlates to SGP's agentex_deploys.id."
    )
    helm_release_name: str | None = Field(
        None, description="Helm release name for cleanup."
    )

    # Timestamps
    created_at: datetime | None = Field(
        None, description="When the deployment was created."
    )
    promoted_at: datetime | None = Field(
        None, description="When the deployment was promoted to production."
    )
    expires_at: datetime | None = Field(
        None, description="When the deployment was marked for cleanup."
    )
