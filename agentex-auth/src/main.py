from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers.authentication_router import authentication_router
from src.api.routers.authorization_router import authorization_router
from src.api.routers.healthcheck_router import healthcheck_router
from src.config import dependencies
from src.domain.exceptions import GenericException
from src.utils.logging import make_logger

logger = make_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await dependencies.startup_global_dependencies()
    yield
    await dependencies.async_shutdown()
    dependencies.shutdown()


app = FastAPI(
    title="Agentex Authentication API",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authorization_router)
app.include_router(authentication_router)
app.include_router(healthcheck_router)


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


@app.get("/")
def read_root():
    return {"Agentex": "Authentication"}
