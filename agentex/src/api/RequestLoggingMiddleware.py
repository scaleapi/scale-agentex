from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.utils.logging import ctx_var_request_id


class RequestLoggingMiddleware:
    """Share one request ID through the response and reset it after streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        request_id = next(
            (
                value.decode("ascii")
                for name, value in headers
                if name.lower() == b"x-request-id"
                and 0 < len(value) <= 128
                and all(33 <= byte <= 126 for byte in value)
            ),
            uuid4().hex,
        )
        encoded_id = request_id.encode("ascii")
        scope.setdefault("state", {})["request_id"] = request_id
        scope["headers"] = [
            (name, value) for name, value in headers if name.lower() != b"x-request-id"
        ] + [(b"x-request-id", encoded_id)]

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [
                        (name, value)
                        for name, value in message.get("headers", [])
                        if name.lower() != b"x-request-id"
                    ]
                    + [(b"x-request-id", encoded_id)],
                }
            await send(message)

        token = ctx_var_request_id.set(request_id)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            ctx_var_request_id.reset(token)
