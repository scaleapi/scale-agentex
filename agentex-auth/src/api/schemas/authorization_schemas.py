from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuthorizedOperationType(StrEnum):
    create = "create"
    read = "read"
    update = "update"
    delete = "delete"
    execute = "execute"


class AgentexResourceType(StrEnum):
    agent = "agent"
    task = "task"


class AgentexResource(BaseModel):
    type: AgentexResourceType
    selector: str


class OptionalAgentexResource(BaseModel):
    type: AgentexResourceType
    selector: str | None = None


class GrantRequest(BaseModel):
    principal: Any  # Accept arbitrary principal context structure
    resource: AgentexResource
    operation: AuthorizedOperationType


class RevokeRequest(BaseModel):
    principal: Any
    resource: AgentexResource
    operation: AuthorizedOperationType


class CheckRequest(BaseModel):
    principal: Any
    resource: AgentexResource
    operation: AuthorizedOperationType


class ResourcesRequest(BaseModel):
    principal: Any
    filter_resource: AgentexResourceType
    filter_operation: AuthorizedOperationType


class AuthorizationResponse(BaseModel):
    success: Literal[True] = True
    metadata: dict | None = None


class ResourcesAuthorizationResponse(BaseModel):
    items: list[str] = Field(description="resource ids principal has access to")
    success: Literal[True] = True
    metadata: dict | None = None
