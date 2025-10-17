from typing import Annotated, Any

from fastapi import Depends
from pydantic import BaseModel, ValidationError
from src.adapters.authorization.adapter_sgp_authorization import DSGPAuthorization
from src.adapters.authorization.port import AuthorizationGateway
from src.api.schemas.authorization_schemas import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import EnvVarKeys, Provider
from src.domain.exceptions import ServiceError, UnprocessableEntity


class AuthorizationService:
    def __init__(
        self,
        provider: DEnvironmentVariable(EnvVarKeys.AUTH_PROVIDER),
        sgp_authz_gateway: DSGPAuthorization,
    ):
        self.provider = provider
        self.registry: dict[Provider, AuthorizationGateway] = {
            Provider.sgp: sgp_authz_gateway,
        }

    def _gateway(self) -> AuthorizationGateway:
        if self.provider not in self.registry:
            raise ServiceError("Provider not supported")
        return self.registry[self.provider]

    def _validate_principal(
        self, gateway: AuthorizationGateway, raw_principal: Any
    ) -> Any:
        expected_type = gateway.principal_type

        if isinstance(raw_principal, expected_type):
            return raw_principal

        try:
            if issubclass(expected_type, BaseModel):
                return expected_type.model_validate(raw_principal)

            return expected_type(raw_principal)

        except (ValidationError, TypeError, ValueError) as e:
            raise UnprocessableEntity(
                f"Principal validation failed: expected {expected_type.__name__}, "
                f"got {type(raw_principal).__name__} that cannot be converted. Error: {str(e)}"
            ) from e

    async def grant(
        self,
        principal,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        gateway = self._gateway()
        validated_principal = self._validate_principal(gateway, principal)
        # The gateway now throws exceptions directly
        await gateway.grant(validated_principal, resource, operation)

    async def revoke(
        self,
        principal,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        gateway = self._gateway()
        validated_principal = self._validate_principal(gateway, principal)
        # The gateway now throws exceptions directly
        await gateway.revoke(validated_principal, resource, operation)

    async def check(
        self,
        principal,
        resource: AgentexResource,
        operation: AuthorizedOperationType,
    ) -> None:
        gateway = self._gateway()
        validated_principal = self._validate_principal(gateway, principal)
        # The gateway now throws exceptions directly
        await gateway.check(validated_principal, resource, operation)

    async def list_resources(
        self,
        principal,
        filter_resource: AgentexResourceType,
        filter_operation: AuthorizedOperationType,
    ) -> list[str]:
        gateway = self._gateway()
        validated_principal = self._validate_principal(gateway, principal)
        # The gateway now throws exceptions directly and returns the list directly
        return await gateway.list_resources(
            validated_principal, filter_resource, filter_operation
        )


DAuthorizationService = Annotated[AuthorizationService, Depends(AuthorizationService)]
