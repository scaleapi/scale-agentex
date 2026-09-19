from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Request

from src.adapters.authorization.adapter_agentex_authz_proxy import (
    DAgentexAuthorization,
)
from src.api.authentication_middleware import DAuthorizationEnabled
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AuthorizationService:
    def __init__(
        self,
        enabled: DAuthorizationEnabled,
        gateway: DAgentexAuthorization,
        request: Request,  # contains the principal context
    ):
        self.gateway = gateway
        self.request = request
        self.principal_context = request.state.principal_context
        self.agent_identity = request.state.agent_identity
        self.enabled = enabled

    def _bypass_check(self) -> bool:
        """Bypass authorization checks for agent-to-agent calls or when disabled.

        Used for check() and list_resources() operations where we trust agent identity.
        """
        if self.agent_identity:
            return True
        return not self.is_enabled()

    def _bypass_write(self) -> bool:
        """Bypass authorization writes only when authorization is disabled.

        Used for grant() and revoke() operations. We do NOT bypass these for
        agent_identity because permission records must still be created so that
        users can access agent-created resources (tasks, etc.) from the UI.
        """
        return not self.is_enabled()

    def is_enabled(self) -> bool:
        return self.enabled

    async def grant(
        self, resource: AgentexResource, *, commit: bool = True, principal_context=...
    ) -> None:
        if self._bypass_write():
            logger.info(
                f"Authorization bypassed for grant operation on resource {resource}"
            )
            return None

        logger.info(
            "[authorization_service] Granting %s permission on %s:%s",
            AuthorizedOperationType.create,
            resource.type,
            resource.selector,
        )
        result = await self.gateway.grant(
            principal_context
            if principal_context is not ...
            else self.principal_context,
            resource,
            AuthorizedOperationType.create,
        )
        return result

    async def revoke(
        self, resource: AgentexResource, *, commit: bool = True, principal_context=...
    ) -> None:
        if self._bypass_write():
            logger.info("Authorization bypassed for revoke operation")
            return None

        logger.info(
            "[authorization_service] Revoking %s permission on %s:%s",
            AuthorizedOperationType.delete,
            resource.type,
            resource.selector,
        )

        result = await self.gateway.revoke(
            principal_context
            if principal_context is not ...
            else self.principal_context,
            resource,
            AuthorizedOperationType.delete,
        )
        logger.info(
            f"Revoked {AuthorizedOperationType.delete} permission on {resource.type}:{resource.selector}"
        )
        return result

    async def check(
        self,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
        *,
        principal_context=...,
    ) -> bool:
        if self._bypass_check():
            logger.info("Authorization bypassed for check operation")
            return True

        # Determine which principal context to use
        effective_principal = (
            principal_context
            if principal_context is not ...
            else self.principal_context
        )

        logger.info(
            "[authorization_service] Checking %s permission on %s:%s",
            operation,
            resource.type,
            resource.selector,
        )
        result = await self.gateway.check(
            effective_principal,
            resource,
            operation,
        )

        logger.info(
            f"Authorization check for {operation} on {resource.type}:{resource.selector}: {'allowed' if result else 'denied'}"
        )
        return result

    async def list_resources(
        self,
        filter_resource: AgentexResourceType,
        filter_operation: AuthorizedOperationType = AuthorizedOperationType.read,
        *,
        principal_context=...,
    ) -> Iterable[str] | None:
        """List resource identifiers for which the current principal has *filter_operation* permission."""

        if self._bypass_check():
            logger.info("Authorization bypassed for list_resources operation")
            return None

        logger.info(
            "[authorization_service] Listing resources of type %s with %s permission",
            filter_resource,
            filter_operation,
        )
        result = await self.gateway.list_resources(
            principal_context
            if principal_context is not ...
            else self.principal_context,
            filter_resource,
            filter_operation,
        )
        logger.info(
            f"Listed resources of type {filter_resource} with {filter_operation} permission"
        )
        return result

    async def register_resource(
        self,
        resource: AgentexResource,
        parent: AgentexResource | None = None,
        *,
        principal_context=...,
    ) -> None:
        """Register a newly created resource with the principal as owner.

        Prefer this over ``grant`` when the resource's authorization schema has
        a parent relation that permissions cascade through (e.g.
        ``agent_api_key`` declares ``parent_agent``). Pass ``parent`` to
        link the child to its parent atomically; without it the cascade
        fails closed.
        """
        if self._bypass():
            logger.info(f"Authorization bypassed for register_resource on {resource}")
            return None

        effective_principal = (
            principal_context
            if principal_context is not ...
            else self.principal_context
        )
        logger.info(
            "[authorization_service] Registering %s:%s (parent=%s)",
            resource.type,
            resource.selector,
            f"{parent.type}:{parent.selector}" if parent is not None else None,
        )
        await self.gateway.register_resource(effective_principal, resource, parent)

    async def deregister_resource(
        self,
        resource: AgentexResource,
        *,
        principal_context=...,
    ) -> None:
        """Deregister a deleted resource and all of its relationships."""
        if self._bypass():
            logger.info(f"Authorization bypassed for deregister_resource on {resource}")
            return None

        effective_principal = (
            principal_context
            if principal_context is not ...
            else self.principal_context
        )
        logger.info(
            "[authorization_service] Deregistering %s:%s",
            resource.type,
            resource.selector,
        )
        await self.gateway.deregister_resource(effective_principal, resource)


DAuthorizationService = Annotated[AuthorizationService, Depends(AuthorizationService)]
