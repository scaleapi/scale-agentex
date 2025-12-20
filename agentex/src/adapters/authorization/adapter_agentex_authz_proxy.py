from collections.abc import Iterable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from src.adapters.authorization.port import (
    AuthorizationGateway,
)
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.principal_context import AgentexAuthPrincipalContext
from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import EnvVarKeys
from src.utils.http_request_handler import HttpRequestHandler


class AgentexAuthorizationProxy(AuthorizationGateway[AgentexAuthPrincipalContext]):
    def __init__(
        self,
        agentex_auth_url: DEnvironmentVariable(EnvVarKeys.AGENTEX_AUTH_URL),
    ):
        self.agentex_auth_url = agentex_auth_url

    async def grant(
        self,
        principal: AgentexAuthPrincipalContext,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        payload = {
            "principal": principal,
            "resource": resource.model_dump(),
            "operation": operation,
        }
        await HttpRequestHandler.post_with_error_handling(
            self.agentex_auth_url, "/v1/authz/grant", json=payload
        )

    async def revoke(
        self,
        principal: AgentexAuthPrincipalContext,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        payload = {
            "principal": principal,
            "resource": resource.model_dump(),
            "operation": operation,
        }
        await HttpRequestHandler.post_with_error_handling(
            self.agentex_auth_url, "/v1/authz/revoke", json=payload
        )

    async def check(
        self,
        principal: AgentexAuthPrincipalContext,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> bool:
        payload = {
            "principal": principal,
            "resource": resource.model_dump(),
            "operation": operation,
        }
        await HttpRequestHandler.post_with_error_handling(
            self.agentex_auth_url, "/v1/authz/check", json=payload
        )
        return True  # request was successful

    async def list_resources(
        self,
        principal: AgentexAuthPrincipalContext,
        filter_resource: AgentexResourceType,
        filter_operation: AuthorizedOperationType = AuthorizedOperationType.read,
    ) -> Iterable[str]:
        payload = {
            "principal": principal,
            "filter_resource": filter_resource,
            "filter_operation": filter_operation,
        }
        response = await HttpRequestHandler.post_with_error_handling(
            self.agentex_auth_url, "/v1/authz/search", json=payload
        )
        return response["items"]


@lru_cache(maxsize=1)
def _get_cached_agentex_authorization() -> AgentexAuthorizationProxy:
    """Cached AgentexAuthorizationProxy instance."""
    from src.config.dependencies import resolve_environment_variable_dependency

    url = resolve_environment_variable_dependency(EnvVarKeys.AGENTEX_AUTH_URL)
    return AgentexAuthorizationProxy(agentex_auth_url=url)


def _get_agentex_authorization() -> AgentexAuthorizationProxy:
    return _get_cached_agentex_authorization()


DAgentexAuthorization = Annotated[
    AgentexAuthorizationProxy, Depends(_get_agentex_authorization)
]
