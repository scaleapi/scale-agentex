from collections.abc import Callable

from fastapi import BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from starlette.background import BackgroundTask

from src.utils.logging import ctx_var_request_id, make_logger
from src.utils.request_utils import (
    decode_request_body,
    form_data_to_body,
    strip_sensitive_items,
)

logger = make_logger(__name__)


def log_request(
    request_id: str,
    request: Request,
    request_body: bytes,
):
    raw_path = request.scope["root_path"] + request.scope["route"].path
    request_dict = decode_request_body(request_body)
    logger.info(
        f"Request [{request.method} {raw_path}] ({request_id}): {request_dict}",
        extra={
            "method": request.method,
            "path": raw_path,
            "query_params": request.query_params,
            "headers": strip_sensitive_items(request.headers),
            "body": request_dict,
            "request_id": request_id,
        },
    )


def log_response(request_id: str, request: Request, response: Response):
    logger.info(
        f"Response[{response.status_code}] [{request.method} {request.url.path}] ({request_id})",
        extra={
            "status_code": response.status_code,
            "method": request.method,
            "path": request.url.path,
            "headers": response.headers,
            "request_id": request_id,
        },
    )


class StreamResponseError(Exception):
    def __init__(self, exception: Exception):
        self.exception = exception


class LoggedStreamingResponse(StreamingResponse):
    def __init__(self, request_id, request, request_body, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_id = request_id
        self.request = request
        self.request_body = request_body

    async def stream_response(self, send) -> None:
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )

            async for chunk in self.body_iterator:
                chunk_bytes = (
                    chunk if isinstance(chunk, bytes) else chunk.encode(self.charset)
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk_bytes,
                        "more_body": True,
                    }
                )

            log_response(self.request_id, self.request, self)

            await send({"type": "http.response.body", "body": b"", "more_body": False})

        except Exception as exc:
            logger.error(f"Error in stream response: {exc}", exc_info=True)
            # Wrap error and propagate up for middlewares to handle
            raise StreamResponseError(exc) from exc


class LoggedAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        # Need to capture a reference to the original factory - but not call it since it has the wrong
        # dependency instantiation
        original_get_route_handler = super().get_route_handler

        def add_logging_to_background_tasks(
            response: Response, request_id: str, request: Request
        ) -> BackgroundTasks | BackgroundTask:
            logging_task = BackgroundTask(log_response, request_id, request, response)
            if isinstance(response.background, BackgroundTasks):
                response.background.add_task(logging_task)
                return response.background
            else:
                return logging_task

        async def _parse_request_body(request: Request) -> bytes:
            content_type = request.headers.get("Content-Type", "")
            if (
                content_type == "application/x-www-form-urlencoded"
                or content_type.startswith("multipart/form-data")
            ):
                try:
                    form_data = await request.form()
                    return form_data_to_body(form_data)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse form data for request {request.url.path}: {e}"
                    )
            return await request.body()

        async def custom_route_handler(request: Request) -> Response:
            request_body = await _parse_request_body(request)
            request_id = ctx_var_request_id.get()
            log_request(request_id, request, request_body)
            response = await original_get_route_handler()(request)
            if isinstance(response, StreamingResponse):
                return LoggedStreamingResponse(
                    request_id=request_id,
                    request=request,
                    request_body=request_body,
                    content=response.body_iterator,
                    status_code=response.status_code,
                    headers=response.headers,
                    media_type=response.media_type,
                    background=response.background,
                )
            else:
                response.background = add_logging_to_background_tasks(
                    response, request_id, request
                )
                return response

        return custom_route_handler
