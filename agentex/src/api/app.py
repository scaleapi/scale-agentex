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
from src.api.authentication_middleware import AgentexAuthMiddleware
from src.api.logged_api_route import LoggedAPIRoute
from src.api.RequestLoggingMiddleware import RequestLoggingMiddleware
from src.api.routes import (
    agent_api_keys,
    agent_task_tracker,
    agents,
    deployment_history,
    events,
    health,
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


async def _initialize_service_container(app: FastAPI):
    """
    Initialize singleton services and store them on app.state.
    This bypasses FastAPI's per-request DI overhead for stateless services.
    """
    from src.adapters.temporal.adapter_temporal import get_temporal_adapter
    from src.config.dependencies import (
        _get_cached_agent_repository,
        _get_cached_deployment_history_repository,
    )

    # Initialize repositories (already cached, but ensure they're created)
    agent_repo = _get_cached_agent_repository()
    deployment_history_repo = _get_cached_deployment_history_repository()
    temporal_adapter = await get_temporal_adapter()

    # Create and cache the use case
    from src.domain.use_cases.agents_use_case import AgentsUseCase

    agents_use_case = AgentsUseCase(
        agent_repository=agent_repo,
        deployment_history_repository=deployment_history_repo,
        temporal_adapter=temporal_adapter,
    )

    # Store on app.state for direct access in routes
    app.state.agents_use_case = agents_use_case
    app.state.agent_repository = agent_repo

    logger.info("Service container initialized on app.state")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await dependencies.startup_global_dependencies()
    await _initialize_service_container(app)
    configure_statsd()
    yield
    await dependencies.async_shutdown()
    dependencies.shutdown()


app = FastAPI(
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Authentication middleware
app.add_middleware(AgentexAuthMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Mount the MkDocs site
docs_path = Path(__file__).parent.parent.parent / "docs" / "site"
if docs_path.exists():
    app.mount("/docs", StaticFiles(directory=str(docs_path), html=True), name="docs")


def format_error_response(detail: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"message": detail, "code": status_code, "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logger.error(f"{request}: {exc_str}")
    content = {"status_code": 10422, "message": exc_str, "data": None}
    return JSONResponse(
        content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


@app.exception_handler(ItemDoesNotExist)
async def handle_missing(request, exc: ItemDoesNotExist):
    return format_error_response(str(exc), 404)


@app.exception_handler(GenericException)
async def handle_generic(request, exc):
    return format_error_response(exc.message, exc.code)


@app.exception_handler(HTTPException)
async def handle_http_exc(request, exc):
    return format_error_response(exc.detail, exc.status_code)


@app.exception_handler(Exception)
async def handle_unexpected(request, exc):
    logger.exception("Unhandled exception caught by exception handler", exc_info=exc)
    return format_error_response(
        f"Internal Server Error. Class: {exc.__class__}. Exception: {exc}", 500
    )


# Include all routers
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(messages.router)
app.include_router(spans.router)
app.include_router(states.router)
app.include_router(health.router)
app.include_router(events.router)
app.include_router(agent_task_tracker.router)
app.include_router(agent_api_keys.router)
app.include_router(deployment_history.router)
app.include_router(schedules.router)
