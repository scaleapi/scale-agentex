from src.adapters.authentication.port import AuthenticationGateway
from src.api.schemas.principal_context import AgentexAuthPrincipalContext
from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import Environment, EnvVarKeys
from src.utils.http_request_handler import HttpRequestHandler


class AgentexAuthenticationProxy(AuthenticationGateway[AgentexAuthPrincipalContext]):
    def __init__(
        self,
        agentex_auth_url: DEnvironmentVariable(EnvVarKeys.AGENTEX_AUTH_URL),
        environment: DEnvironmentVariable(EnvVarKeys.ENVIRONMENT),
    ):
        self.agentex_auth_url = agentex_auth_url
        self.environment = Environment(environment) if environment else Environment.DEV

    async def verify_headers(
        self, headers: dict[str, str]
    ) -> AgentexAuthPrincipalContext:
        return await HttpRequestHandler.post_with_error_handling(
            self.agentex_auth_url, "/v1/authn", headers=headers
        )
