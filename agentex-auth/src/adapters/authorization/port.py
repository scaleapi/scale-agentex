from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

from src.api.schemas.authorization_schemas import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)

PrincipalT = TypeVar("PrincipalT")


class AuthorizationGateway(Generic[PrincipalT], ABC):
    """Abstract interface for authorization gateways."""

    principal_type: ClassVar[type[PrincipalT]]

    @abstractmethod
    async def grant(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> dict[str, Any]:
        """
        Persist a new (principal, resource, operation) edge.

        Returns:
            Permission details

        Raises:
            AuthorizationError: For authorization failures (403)
            AuthorizationUnauthorizedError: For unauthorized access (401)
            AuthorizationGatewayError: For gateway errors (502)
            AuthorizationServiceUnavailableError: For service unavailable (503)
        """

    @abstractmethod
    async def revoke(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        """
        Delete an existing edge.

        Raises:
            AuthorizationError: For authorization failures (403)
            AuthorizationUnauthorizedError: For unauthorized access (401)
            AuthorizationGatewayError: For gateway errors (502)
            AuthorizationServiceUnavailableError: For service unavailable (503)
        """

    @abstractmethod
    async def check(
        self,
        principal: PrincipalT,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        """
        Check if principal has operation on resource.

        Raises:
            AuthorizationError: If principal lacks permission
            AuthorizationUnauthorizedError: For unauthorized access (401)
            AuthorizationGatewayError: For gateway errors (502)
            AuthorizationServiceUnavailableError: For service unavailable (503)
        """

    @abstractmethod
    async def list_resources(
        self,
        principal: PrincipalT,
        filter_resource: AgentexResourceType,
        filter_operation: AuthorizedOperationType,
    ) -> list[str]:
        """
        List resources that principal has access to.

        Returns:
            List of resource selectors

        Raises:
            AuthorizationError: For authorization failures (403)
            AuthorizationUnauthorizedError: For unauthorized access (401)
            AuthorizationGatewayError: For gateway errors (502)
            AuthorizationServiceUnavailableError: For service unavailable (503)
        """
