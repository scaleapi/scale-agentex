from typing import Annotated

from fastapi import Depends
from src.adapters.authentication.port import AuthenticationGateway
from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import EnvVarKeys
from src.domain.models.principal_contexts import SGPPrincipalContext
from src.utils.make_authenticated_request import make_authenticated_request


class SGPAuthentication(AuthenticationGateway):
    def __init__(
        self,
        sgp_base_url: DEnvironmentVariable(EnvVarKeys.AUTH_PROVIDER_BASE_URL),
    ):
        self.sgp_base_url = sgp_base_url

    async def verify_headers(
        self,
        headers: dict[str, str],
    ) -> SGPPrincipalContext:
        headers_cleaned = {
            key: value
            for key, value in {
                "x-api-key": headers.get("x-api-key"),
                "x-selected-account-id": headers.get("x-selected-account-id"),
                "cookie": headers.get("cookie"),
            }.items()
            if value is not None
        }

        # This will throw appropriate exceptions on error
        response = await make_authenticated_request(
            base_url=self.sgp_base_url,
            method="GET",
            path="/public/user-info",
            headers=headers_cleaned,
        )

        user_info = response.json()
        account_id = headers.get("x-selected-account-id") or response.headers.get(
            "x-selected-account-id"
        )

        principal_context = SGPPrincipalContext(
            user_id=user_info["id"],
            account_id=account_id,
            raw_user=user_info,
            metadata={},
        )
        return principal_context


DSGPAuthentication = Annotated[SGPAuthentication, Depends(SGPAuthentication)]
