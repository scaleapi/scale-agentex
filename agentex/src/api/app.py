import os
from contextlib import asynccontextmanager
from pathlib import Path

from datadog import initialize, statsd
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.http.adapter_httpx import HttpxGateway
from src.api.authentication_middleware import AgentexAuthMiddleware
from src.api.health_interceptor import HealthCheckInterceptor
from src.api.logged_api_route import LoggedAPIRoute
from src.api.RequestLoggingMiddleware import RequestLoggingMiddleware
from src.api.routes import (
    agent_api_keys,
    agent_task_tracker,
    agents,
    deployment_history,
    events,
    messages,
    schedules,
    spans,
    states,
    tasks,
)
from src.config import dependencies
from src.config.dependencies import resolve_environment_variable_dependency
from src.config.environment_variables import EnvVarKeys
from src.domain.exceptions import GenericException
from src.utils.logging import make_logger

logger = make_logger(__name__)


def configure_statsd():
    """Configure the global DataDog StatsD client"""
    initialize(
        statsd_host=os.getenv("DD_AGENT_HOST", "localhost"),
        statsd_port=int(os.getenv("DD_STATSD_PORT", "8125")),
    )
    return statsd


class HTTPExceptionWithMessage(HTTPException):
    """
    HTTPException with request ID header.
    """

    message: str | None

    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
        message: str | None = None,
    ):
        headers = headers or {}
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.message = message


@asynccontextmanager
async def lifespan(_: FastAPI):
    await dependencies.startup_global_dependencies()
    configure_statsd()
    yield
    # Clean up HTTP clients before other shutdown tasks
    await HttpxGateway.close_clients()
    await dependencies.async_shutdown()
    dependencies.shutdown()


fastapi_app = FastAPI(
    title="Agentex API",
    openapi_url="/openapi.json",
    docs_url="/swagger",
    redoc_url="/api",
    swagger_ui_oauth2_redirect_url="/swagger/oauth2-redirect",
    root_path="",
    root_path_in_servers=False,
    lifespan=lifespan,
    route_class=LoggedAPIRoute,
    separate_input_output_schemas=False,
)

# Add CORS middleware
allowed_origins = resolve_environment_variable_dependency(EnvVarKeys.ALLOWED_ORIGINS)
allowed_origins_list = (
    [origin.strip() for origin in allowed_origins.split(",")]
    if allowed_origins and isinstance(allowed_origins, str)
    else ["*"]
)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Authentication middleware
fastapi_app.add_middleware(AgentexAuthMiddleware)
fastapi_app.add_middleware(RequestLoggingMiddleware)

# Mount the MkDocs site
docs_path = Path(__file__).parent.parent.parent / "docs" / "site"
if docs_path.exists():
    fastapi_app.mount(
        "/docs", StaticFiles(directory=str(docs_path), html=True), name="docs"
    )


def format_error_response(detail: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"message": detail, "code": status_code, "data": None},
    )


@fastapi_app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logger.error(f"{request}: {exc_str}")
    content = {"status_code": 10422, "message": exc_str, "data": None}
    return JSONResponse(
        content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


@fastapi_app.exception_handler(ItemDoesNotExist)
async def handle_missing(request, exc: ItemDoesNotExist):
    return format_error_response(str(exc), 404)


@fastapi_app.exception_handler(GenericException)
async def handle_generic(request, exc):
    return format_error_response(exc.message, exc.code)


@fastapi_app.exception_handler(HTTPException)
async def handle_http_exc(request, exc):
    return format_error_response(exc.detail, exc.status_code)


@fastapi_app.exception_handler(Exception)
async def handle_unexpected(request, exc):
    logger.exception("Unhandled exception caught by exception handler", exc_info=exc)
    return format_error_response(
        f"Internal Server Error. Class: {exc.__class__}. Exception: {exc}", 500
    )


# Include all routers
fastapi_app.include_router(agents.router)
fastapi_app.include_router(tasks.router)
fastapi_app.include_router(messages.router)
fastapi_app.include_router(spans.router)
fastapi_app.include_router(states.router)
fastapi_app.include_router(events.router)
fastapi_app.include_router(agent_task_tracker.router)
fastapi_app.include_router(agent_api_keys.router)
fastapi_app.include_router(deployment_history.router)
fastapi_app.include_router(schedules.router)

# Wrap FastAPI app with health check interceptor for sub-millisecond K8s probe responses.
# This must be the outermost layer to bypass all middleware.
# Export as `app` so existing uvicorn entry points (app:app) work without changes.
app = HealthCheckInterceptor(fastapi_app)
