from datetime import datetime

from pydantic import Field

from src.utils.model_utils import BaseModel


class DeploymentHistory(BaseModel):
    """API schema for deployment history."""

    id: str = Field(..., description="The unique identifier of the deployment record")
    agent_id: str = Field(
        ..., description="The ID of the agent this deployment belongs to"
    )

    # Build and commit metadata
    author_name: str = Field(..., description="Name of the commit author")
    author_email: str = Field(..., description="Email of the commit author")
    branch_name: str = Field(..., description="Name of the branch")
    build_timestamp: datetime = Field(..., description="When the build was created")
    deployment_timestamp: datetime = Field(
        ..., description="When this deployment was first seen in the system"
    )
    commit_hash: str = Field(..., description="Git commit hash for this deployment")
