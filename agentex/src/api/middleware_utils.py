from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from src.adapters.authentication.adapter_agentex_authn_proxy import (
    AgentexAuthenticationProxy,
)
from src.adapters.orm import AgentAPIKeyORM, AgentORM
from src.config.dependencies import middleware_async_read_only_session_maker
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Routes (and their prefixes) that bypass authentication
WHITELISTED_ROUTES: set[str] = {
    "/agents/register",
    "/agents/forward",
    "/docs",
    "/api",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/health",
    "/healthcheck",
    "/healthz",
    "/readyz",
    "/ping",
    "/echo",
}

DROP_HEADERS: set[str] = {
    "content-length",
    "host",
    "connection",
    "transfer-encoding",
    "expect",
}


def is_whitelisted_route(
    path: str, whitelisted_routes: set[str] = WHITELISTED_ROUTES
) -> bool:
    """Check if a route path is whitelisted (bypasses authentication)."""
    return path in whitelisted_routes or any(
        path.startswith(route) for route in whitelisted_routes
    )


async def verify_agent_identity(
    request: Request, agent_identity: str
) -> JSONResponse | None:
    """
    Verify agent identity against the database.

    Returns:
        None if agent is valid (authentication should proceed)
        JSONResponse with error if agent is invalid or verification fails
    """
    try:
        # Try to get the agent from the repository
        # Using a separate sessionmaker and sqlalchemy pool so it never gets blocked by the application
        AsyncReadOnlySessionMaker = middleware_async_read_only_session_maker()
        async with AsyncReadOnlySessionMaker() as session:
            agent = await session.scalar(select(AgentORM).filter_by(id=agent_identity))

            if agent:
                request.state.agent_identity = agent.id
                logger.info(f"Authentication gateway verified agent ID {agent.id}")
                return None  # Agent is valid, continue processing
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Agent Unauthorized"},
                )
    except Exception as e:
        logger.error(f"Error verifying agent identity: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Agent authorization failed"},
        )


async def verify_agent_api_key(
    request: Request, agent_api_key: str
) -> JSONResponse | None:
    """
    Verify agent API key against the database.

    Returns:
        None if agent is valid (authentication should proceed)
        JSONResponse with error if agent is invalid or verification fails
    """
    try:
        # Try to get the agent from the repository
        # Using a separate sessionmaker and sqlalchemy pool so it never gets blocked by the application
        AsyncReadOnlySessionMaker = middleware_async_read_only_session_maker()
        async with AsyncReadOnlySessionMaker() as session:
            resolved_api_key = await session.scalar(
                select(AgentAPIKeyORM).filter_by(api_key=agent_api_key)
            )

            if resolved_api_key:
                request.state.agent_identity = resolved_api_key.agent_id
                logger.info(
                    f"Authentication gateway verified API key for agent ID {resolved_api_key.agent_id}"
                )
                return None  # Agent API key is valid, continue processing
            else:
                logger.warning("Invalid agent API key provided")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Agent Unauthorized"},
                )
    except Exception as e:
        logger.error(f"Error verifying agent API key: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Agent authorization failed"},
        )


async def verify_auth_gateway(
    request: Request, auth_gateway: AgentexAuthenticationProxy
) -> JSONResponse | None:
    """
    Verify request through the authentication gateway.

    Returns:
        None if authentication successful (sets principal_context on request.state)
        JSONResponse with error if authentication fails
    """
    headers_dict = get_request_headers_to_forward(request)

    try:
        principal_context = await auth_gateway.verify_headers(headers_dict)
        request.state.principal_context = principal_context

        # Get route information
        route_path = request.url.path
        method = request.method

        logger.info(
            "[authentication_middleware] Request authenticated successfully for %s %s with principal %s",
            method,
            route_path,
            principal_context,
        )
        return None  # Authentication successful
    except Exception as exc:
        logger.error(
            "[authentication_middleware] Request for %s %s failed with %s",
            request.method,
            request.url.path,
            str(exc),
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
        )


def get_request_headers_to_forward(
    request: Request,
    exclude_headers: set[str] = DROP_HEADERS,
) -> dict[str, str]:
    """
    Get headers to forward in a request, excluding specified headers.

    Args:
        request: The incoming request object.
        exclude_headers: Set of header names to exclude from forwarding.

    Returns:
        Dictionary of headers to forward.
    """
    return {
        name.lower(): value
        for name, value in request.headers.items()
        if name.lower() not in exclude_headers
    }


def resolve_authorization_enabled(env_value: str) -> bool:
    """Resolve whether authorization is enabled based on environment variable."""
    logger.info(f"Authorization URL: {env_value}")
    return bool(env_value)
