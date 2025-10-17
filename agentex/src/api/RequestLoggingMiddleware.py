from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.utils.logging import ctx_var_request_id


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # Set a request ID in every logging extra dict so that we can correlate logs for a
        # single request.
        request_id = str(uuid4().hex)
        ctx_var_request_id.set(request_id)
        return await call_next(request)
