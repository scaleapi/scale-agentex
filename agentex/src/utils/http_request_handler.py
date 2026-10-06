import re
from collections.abc import Iterable
from typing import Any

import httpx

from src.adapters.authentication.exceptions import (
    AuthenticationError,
    AuthenticationGatewayError,
    AuthenticationServiceUnavailableError,
)
from src.adapters.authorization.exceptions import (
    AuthorizationError,
)
from src.domain.exceptions import ServiceError
from src.utils.cached_httpx_client import get_async_client
from src.utils.logging import make_logger

logger = make_logger(__name__)

SERVICE_ACCOUNT_AUTH_ERROR_HEADER = "X-Service-Account-Auth-Error"
SERVICE_ACCOUNT_AUTH_ERROR_VALUES = frozenset(
    {"unauthenticated", "forbidden", "unavailable"}
)
_MAX_ERROR_MESSAGE_LENGTH = 200
_CREDENTIAL_HEADER_PATTERN = re.compile(
    r"authorization|cookie|token|key|secret|session|credential|password",
    re.IGNORECASE,
)


class HttpRequestHandler:
    @staticmethod
    async def post_with_error_handling(
        base_url: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make a POST request and automatically raise appropriate exceptions based on response.

        Error handling logic:
        - X-Service-Account-Auth-Error → Service unavailable error (this
          service's own identity was rejected, not the user's credentials)
        - 3xx → Gateway error (redirects are not followed)
        - 401 → AuthenticationError
        - 403 → AuthorizationError
        - 5xx → Service unavailable error
        - Other non-200 → Service error with details
        - Network errors → ServiceUnavailableError

        Args:
            base_url: The base URL for the service
            path: The endpoint path
            json: JSON payload
            headers: Request headers

        Returns:
            The JSON response as a dictionary

        Raises:
            AuthenticationError: For 401 Unauthorized
            AuthorizationError: For 403 Forbidden
            ServiceError: For server errors or unexpected responses
        """
        client = get_async_client(base_url)
        secrets = _credential_values(headers)

        try:
            # Auth credentials must not be forwarded to a redirect destination.
            response = await client.post(
                path, json=json, headers=headers, follow_redirects=False
            )
        except httpx.RequestError as err:
            # Network/timeout errors
            error_detail = str(err)
            if hasattr(err, "request") and err.request:
                error_detail = f"Request to {err.request.url} failed: {error_detail}"

            raise AuthenticationServiceUnavailableError(
                message="Service unreachable or timed out",
                detail=_redact(error_detail, secrets),
            ) from err

        if response.status_code == 200:
            try:
                return response.json()
            except Exception as err:
                raise ServiceError(
                    message="Failed to parse response",
                    detail=f"Invalid JSON: {str(err)}",
                ) from err

        # Extract error message from response if possible
        # Redact before truncating so a cut cannot leave a partial credential.
        error_message = (
            _redact(HttpRequestHandler._extract_error_message(response), secrets)
            or _redact(response.text, secrets)
            or ""
        )[:_MAX_ERROR_MESSAGE_LENGTH]

        service_account_error = response.headers.get(SERVICE_ACCOUNT_AUTH_ERROR_HEADER)
        if service_account_error is not None:
            reason = service_account_error.strip().lower()
            if reason not in SERVICE_ACCOUNT_AUTH_ERROR_VALUES:
                reason = "unrecognized"
            logger.error(
                "Auth provider rejected this service's identity on %s: "
                "%s=%s (status %s)",
                path,
                SERVICE_ACCOUNT_AUTH_ERROR_HEADER,
                reason,
                response.status_code,
            )
            raise AuthenticationServiceUnavailableError(
                message=f"Auth provider rejected this service's identity ({reason})",
                detail=error_message,
            )

        if 300 <= response.status_code < 400:
            raise AuthenticationGatewayError(
                message=(
                    f"Auth provider returned redirect status {response.status_code} "
                    f"for {path}; redirects are not followed, so configure the "
                    "provider URL with its final origin"
                ),
            )

        if response.status_code == 401:
            raise AuthenticationError(
                message=error_message or "Unauthorized – missing or invalid credentials"
            )

        if response.status_code == 403:
            raise AuthorizationError(
                message=error_message or "Forbidden – principal lacks permission"
            )

        if response.status_code >= 500:
            raise AuthenticationServiceUnavailableError(
                message=f"Auth provider error (status {response.status_code})",
                detail=error_message,
            )

        raise ServiceError(
            message=f"Unexpected response status {response.status_code}",
            code=response.status_code,
            detail=error_message,
        )

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str | None:
        """Extract error message from response if possible."""
        try:
            data = response.json()
            # Common error message fields
            for field in ["message", "error", "detail", "description"]:
                if field in data:
                    return str(data[field])
            # If it's a dict with a single key, try that
            if isinstance(data, dict) and len(data) == 1:
                return str(list(data.values())[0])
        except Exception:
            # If JSON parsing fails, try to return some text
            if response.text:
                return response.text
        return None


def _credential_values(headers: dict[str, str] | None) -> list[str]:
    return [
        value
        for name, value in (headers or {}).items()
        if _CREDENTIAL_HEADER_PATTERN.search(name)
    ]


def _redact(text: str | None, secrets: Iterable[str]) -> str | None:
    """Remove outbound header values (credentials) a provider may echo back."""
    if not text:
        return text
    candidates = set()
    for value in secrets:
        candidates.add(value)
        for part in re.split(r"[\s;,]+", value):
            candidates.add(part)
            _, sep, rest = part.partition("=")
            if sep and rest.strip("="):
                candidates.add(rest)
            elif rest:
                # Trailing base64 padding; providers may echo it stripped.
                candidates.add(part.rstrip("="))
    candidates.discard("")
    if not candidates:
        return text
    # One pass, longest first, so a replacement is never rescanned.
    pattern = "|".join(
        re.escape(candidate) for candidate in sorted(candidates, key=len, reverse=True)
    )
    return re.sub(pattern, "[REDACTED]", text)
