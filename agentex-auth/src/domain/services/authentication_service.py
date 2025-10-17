from typing import Annotated, Any

from fastapi import Depends
from src.adapters.authentication.adapter_sgp_auth import DSGPAuthentication
from src.adapters.authentication.port import AuthenticationGateway
from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import EnvVarKeys, Provider
from src.domain.exceptions import ServiceError
from src.utils.logging import make_logger

PrincipalContext = Any

logger = make_logger(__name__)


class AuthenticationService:
    def __init__(
        self,
        provider: DEnvironmentVariable(EnvVarKeys.AUTH_PROVIDER),
        sgp_auth_gateway: DSGPAuthentication,
    ):
        self.provider = provider
        self.registry: dict[Provider, AuthenticationGateway] = {
            Provider.sgp: sgp_auth_gateway
        }

    def _gateway(self) -> AuthenticationGateway:
        if self.provider not in self.registry:
            raise ServiceError("Provider not supported")
        return self.registry[self.provider]

    async def verify_headers(self, headers: dict[str, str]) -> PrincipalContext:
        logger.info("[authentication_service] Calling /v1/authn")
        # The gateway now throws exceptions directly, no need to handle results
        return await self._gateway().verify_headers(headers)


DAuthenticationService = Annotated[
    AuthenticationService, Depends(AuthenticationService)
]
