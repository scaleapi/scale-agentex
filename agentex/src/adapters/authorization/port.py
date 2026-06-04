from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Generic, TypeVar

from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)

PrincipalT = TypeVar("PrincipalT")


class AuthorizationGateway(Generic[PrincipalT], ABC):
    @abstractmethod
    async def grant(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        """Persist a new (principal, resource, permission) edge."""

    @abstractmethod
    async def revoke(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        """Invalidate an existing edge."""

    @abstractmethod
    async def check(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> bool:
        """Return True iff *principal* can do *operation* on *resource*."""

    @abstractmethod
    async def list_resources(
        self,
        principal: PrincipalT,
        filter_resource: AgentexResourceType,
        filter_operation: AuthorizedOperationType = AuthorizedOperationType.read,
    ) -> Iterable[str]:
        """List resource_ids for a given principal"""

    @abstractmethod
    async def register_resource(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        parent: AgentexResource | None = None,
    ) -> None:
        """Register a newly created resource with the principal as owner.
        Optionally writes a lifecycle parent edge.

        Use this on resource create instead of ``grant`` when the resource
        type's authorization schema has a parent relation that permission
        checks cascade through (e.g. ``agent_api_key`` declares
        ``parent_agent``). Without writing that edge here the cascade fails
        closed.
        """

    @abstractmethod
    async def deregister_resource(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
    ) -> None:
        """Deregister a deleted resource and all of its relationships
        (owner, parent, grantees) in a single atomic call."""
