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
