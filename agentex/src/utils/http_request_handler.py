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
        - 401 → AuthenticationError
        - 403 → AuthorizationError
        - 502 → Gateway error (bad gateway)
        - 503+ → Service unavailable error
        - Other 5xx → Service error
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

        try:
            response = await client.post(path, json=json, headers=headers)
        except httpx.RequestError as err:
            # Network/timeout errors
            error_detail = str(err)
            if hasattr(err, "request") and err.request:
                error_detail = f"Request to {err.request.url} failed: {error_detail}"

            raise AuthenticationServiceUnavailableError(
                message="Service unreachable or timed out", detail=error_detail
            ) from err

        # Extract error message from response if possible
        error_message = HttpRequestHandler._extract_error_message(response)

        # Handle specific status codes
        if response.status_code == 401:
            raise AuthenticationError(
                message=error_message or "Unauthorized – missing or invalid credentials"
            )

        if response.status_code == 403:
            raise AuthorizationError(
                message=error_message or "Forbidden – principal lacks permission"
            )

        # Handle server errors
        if response.status_code == 502:
            raise AuthenticationGatewayError(
                message="Bad gateway", detail=error_message or response.text[:200]
            )

        if response.status_code == 503:
            raise AuthenticationServiceUnavailableError(
                message="Service temporarily unavailable",
                detail=error_message or response.text[:200],
            )

        if response.status_code >= 500:
            raise ServiceError(
                message=f"Server error (status {response.status_code})",
                detail=error_message or response.text[:200],
            )

        # Handle any other non-200 status
        if response.status_code != 200:
            raise ServiceError(
                message=f"Unexpected response status {response.status_code}",
                code=response.status_code,
                detail=error_message or response.text[:200],
            )

        # Parse JSON response
        try:
            return response.json()
        except Exception as err:
            raise ServiceError(
                message="Failed to parse response", detail=f"Invalid JSON: {str(err)}"
            ) from err

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
                return response.text[:200]  # Limit length
        return None
