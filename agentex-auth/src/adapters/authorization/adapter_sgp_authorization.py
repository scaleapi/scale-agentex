from typing import Annotated, Any

from fastapi import Depends
from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.authorization.port import AuthorizationGateway
from src.api.schemas.authorization_schemas import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import EnvVarKeys
from src.domain.models.principal_contexts import SGPPrincipalContext
from src.utils.make_authenticated_request import make_authenticated_request


class SGPAuthorization(AuthorizationGateway[SGPPrincipalContext]):
    """SGP implementation of AuthorizationGateway."""

    principal_type = SGPPrincipalContext

    def __init__(
        self,
        sgp_base_url: DEnvironmentVariable(EnvVarKeys.AUTH_PROVIDER_BASE_URL),
    ):
        self.sgp_base_url = sgp_base_url

    async def grant(
        self,
        principal: SGPPrincipalContext,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> dict[str, Any]:
        headers = self._construct_headers_from_principal(principal)

        request = {
            "principal": {
                "type": "account",
                "selector": principal.account_id,
            },
            "resource": {"type": resource.type, "selector": resource.selector},
            "permission": "owner",
        }

        response = await make_authenticated_request(
            base_url=self.sgp_base_url,
            method="POST",
            path="/private/v5/agentex/permissions",
            headers=headers,
            json=request,
        )

        return response.json()

    async def revoke(
        self,
        principal: SGPPrincipalContext,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        if resource.selector in {"*"}:
            raise AuthorizationError("Cannot revoke permissions for wildcard selectors")

        params = {"resources": [f"{resource.type}:{resource.selector}"]}
        headers = self._construct_headers_from_principal(principal)

        response = await make_authenticated_request(
            base_url=self.sgp_base_url,
            method="GET",
            path="/private/v5/agentex/permissions",
            params=params,
            headers=headers,
        )

        permissions = response.json()
        items = permissions["items"]
        if len(items) != 1:
            raise AuthorizationError(
                f"Expected exactly one permission, found {len(items)}"
            )

        permission_id = items[0]["id"]

        await make_authenticated_request(
            base_url=self.sgp_base_url,
            method="DELETE",
            path=f"/private/v5/agentex/permissions/{permission_id}",
            headers=headers,
        )

    async def check(
        self,
        principal: SGPPrincipalContext,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        headers = self._construct_headers_from_principal(principal)

        request = {
            "resource": {"type": resource.type, "selector": resource.selector},
            "operation": operation,
        }

        response = await make_authenticated_request(
            base_url=self.sgp_base_url,
            method="post",
            path="/private/v5/agentex/permissions/check",
            json=request,
            headers=headers,
        )

        perms = response.json()
        has_permission = perms["has_permission"]
        if not has_permission:
            raise AuthorizationError(
                f"Principal account:{principal.account_id} can not {operation} {resource.type}:{resource.selector}"
            )
        return has_permission

    async def list_resources(
        self,
        principal: SGPPrincipalContext,
        filter_resource: AgentexResourceType,
        filter_operation: AuthorizedOperationType,
    ) -> list[str]:
        params = {"resources": [f"{filter_resource}:*"], "limit": 999}
        headers = self._construct_headers_from_principal(principal)

        response = await make_authenticated_request(
            base_url=self.sgp_base_url,
            method="GET",
            path="/private/v5/agentex/permissions",
            params=params,
            headers=headers,
        )

        permissions = response.json()
        items = permissions.get("items", [])

        if len(items) == 0:
            return []

        selectors: list[str] = [
            p["resource"]["selector"]
            for p in items
            if "resource" in p and "selector" in p["resource"]
        ]

        return selectors

    def _construct_headers_from_principal(self, principal: SGPPrincipalContext):
        headers = {
            "x-api-key": principal.api_key,
            "x-selected-account-id": principal.account_id,
            "x-user-id": principal.user_id,
        }
        return {k: v for k, v in headers.items() if v is not None}


DSGPAuthorization = Annotated[SGPAuthorization, Depends(SGPAuthorization)]
