from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.adapters.authentication.adapter_agentex_authn_proxy import (
    AgentexAuthenticationProxy,
)
from src.api.authentication_cache import get_auth_cache
from src.api.middleware_utils import (
    get_request_headers_to_forward,
    is_whitelisted_route,
    resolve_authorization_enabled,
    verify_agent_api_key,
    verify_agent_identity,
    verify_auth_gateway,
)
from src.config.dependencies import (
    DEnvironmentVariable,
    resolve_environment_variable_dependency,
)
from src.config.environment_variables import EnvVarKeys
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Sentinel value to distinguish between "not in cache" and "cached as failed"
_CACHED_FAILED_AUTH = "__FAILED_AUTH__"


class AgentexAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._enabled = bool(
            resolve_environment_variable_dependency(EnvVarKeys.AGENTEX_AUTH_URL)
        )
        self._auth_gateway = AgentexAuthenticationProxy(
            agentex_auth_url=resolve_environment_variable_dependency(
                EnvVarKeys.AGENTEX_AUTH_URL
            ),
            environment=resolve_environment_variable_dependency(EnvVarKeys.ENVIRONMENT),
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        request.state.principal_context = None
        request.state.agent_identity = None

        # Skip authentication for whitelisted routes
        if is_whitelisted_route(request.url.path):
            logger.info(
                "[authentication_middleware] Authentication skipped for whitelisted route"
            )
            return await call_next(request)

        # Get cache instance (async-safe)
        auth_cache = await get_auth_cache()

        # Handle agent identity authentication
        # TODO: deprecate x-agent-identity in favor of x-agent-api-key
        agent_identity = request.headers.get("x-agent-identity")
        if agent_identity:
            # Check cache first
            cached_agent_id = await auth_cache.get_agent_identity(agent_identity)

            # Check if this is a cached failure
            if cached_agent_id == _CACHED_FAILED_AUTH:
                logger.debug(
                    f"Agent identity {agent_identity} found in cache as failed"
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Agent Unauthorized"},
                )

            # Check if this is a cached success
            if cached_agent_id is not None:
                request.state.agent_identity = cached_agent_id
                logger.debug(f"Agent identity {agent_identity} found in cache")
                return await call_next(request)

            # Not in cache, verify with database
            error_response = await verify_agent_identity(request, agent_identity)
            if error_response:
                # Cache the negative result with sentinel value
                await auth_cache.set_agent_identity(agent_identity, _CACHED_FAILED_AUTH)
                return error_response

            # Cache the successful verification
            await auth_cache.set_agent_identity(
                agent_identity, request.state.agent_identity
            )
            return await call_next(request)

        agent_api_key = request.headers.get("x-agent-api-key")
        if agent_api_key:
            # Check cache first
            cached_agent_id = await auth_cache.get_agent_api_key(agent_api_key)

            # Check if this is a cached failure
            if cached_agent_id == _CACHED_FAILED_AUTH:
                logger.debug("Agent API key found in cache as failed")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Agent Unauthorized"},
                )

            # Check if this is a cached success
            if cached_agent_id is not None:
                request.state.agent_identity = cached_agent_id
                logger.debug("Agent API key found in cache")
                return await call_next(request)

            # Not in cache, verify with database
            error_response = await verify_agent_api_key(request, agent_api_key)
            if error_response:
                # Cache the negative result with sentinel value
                await auth_cache.set_agent_api_key(agent_api_key, _CACHED_FAILED_AUTH)
                return error_response

            # Cache the successful verification
            await auth_cache.set_agent_api_key(
                agent_api_key, request.state.agent_identity
            )
            return await call_next(request)

        # Handle auth gateway authentication (if enabled)
        if self._enabled:
            # Get headers for caching
            headers_dict = get_request_headers_to_forward(request)

            # Check cache first
            cached_principal = await auth_cache.get_auth_gateway_response(headers_dict)
            if cached_principal is not None:
                request.state.principal_context = cached_principal
                logger.debug("Auth gateway response found in cache")
                return await call_next(request)

            # Not in cache, verify with auth gateway
            error_response = await verify_auth_gateway(request, self._auth_gateway)
            if error_response:
                # Don't cache failed authentications for auth gateway
                # as they might be temporary (e.g., expired tokens)
                return error_response

            # Cache the successful authentication
            await auth_cache.set_auth_gateway_response(
                headers_dict, request.state.principal_context
            )

        return await call_next(request)


def _resolve_authorization_enabled(
    env_value: DEnvironmentVariable(EnvVarKeys.AGENTEX_AUTH_URL),
) -> bool:
    return resolve_authorization_enabled(env_value)


DAuthorizationEnabled = Annotated[bool, Depends(_resolve_authorization_enabled)]
