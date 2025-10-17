from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Request

from src.adapters.authorization.adapter_agentex_authz_proxy import DAgentexAuthorization
from src.api.authentication_cache import get_auth_cache
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

    def _bypass(self) -> bool:
        if self.agent_identity:
            return True
        return not self.enabled

    async def grant(
        self, resource: AgentexResource, *, commit: bool = True, principal_context=...
    ) -> None:
        if self._bypass():
            logger.info(
                f"Authorization bypassed for grant operation on resource {resource}"
            )
            return None

        logger.info(
            "[authorization_service] Granting %s permission on %s:%s for principal %s",
            AuthorizedOperationType.create,
            resource.type,
            resource.selector,
            self.principal_context,
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
        if self._bypass():
            logger.info("Authorization bypassed for revoke operation")
            return None

        logger.info(
            "[authorization_service] Revoking %s permission on %s:%s for principal %s",
            AuthorizedOperationType.delete,
            resource.type,
            resource.selector,
            self.principal_context,
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
        if self._bypass():
            logger.info("Authorization bypassed for check operation")
            return True

        # Determine which principal context to use
        effective_principal = (
            principal_context
            if principal_context is not ...
            else self.principal_context
        )

        # Try to get cached result first
        auth_cache = await get_auth_cache()
        cached_result = await auth_cache.get_authorization_check(
            resource_type=str(resource.type),
            resource_selector=resource.selector,
            operation=str(operation),
            principal_context=effective_principal,
        )

        if cached_result is not None:
            logger.info(
                "[authorization_service] Using cached result for %s permission on %s:%s for principal %s: %s",
                operation,
                resource.type,
                resource.selector,
                effective_principal,
                "allowed" if cached_result else "denied",
            )
            return cached_result

        # Not in cache, perform actual check
        logger.info(
            "[authorization_service] Checking %s permission on %s:%s for principal %s",
            operation,
            resource.type,
            resource.selector,
            effective_principal,
        )
        result = await self.gateway.check(
            effective_principal,
            resource,
            operation,
        )

        # Cache the result
        await auth_cache.set_authorization_check(
            resource_type=str(resource.type),
            resource_selector=resource.selector,
            operation=str(operation),
            principal_context=effective_principal,
            allowed=result,
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

        if self._bypass():
            logger.info("Authorization bypassed for list_resources operation")
            return None

        logger.info(
            "[authorization_service] Listing resources of type %s with %s permission for principal %s",
            filter_resource,
            filter_operation,
            self.principal_context,
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


DAuthorizationService = Annotated[AuthorizationService, Depends(AuthorizationService)]
