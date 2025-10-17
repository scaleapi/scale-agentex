from typing import Any

import httpx
from src.adapters.authentication.exceptions import AuthenticationError
from src.adapters.authorization.exceptions import AuthorizationError
from src.domain.exceptions import ClientError, ServiceError, UnprocessableEntity
from src.utils.cached_httpx_client import get_async_client


async def make_authenticated_request(
    base_url: str,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    """
    Make an HTTP request and handle errors by throwing appropriate exceptions.

    Args:
        base_url: Base URL for the service
        method: HTTP method (GET, POST, DELETE, etc.)
        path: URL path
        headers: Optional headers
        params: Optional query parameters
        json: Optional JSON body

    Returns:
        httpx.Response if successful (2xx status code)

    Raises:
        ClientError: For 400 Bad Request
        AuthenticationError: For 401 Unauthorized
        AuthorizationError: For 403 Forbidden
        UnprocessableEntity: For 422 Unprocessable Entity
        ServiceError: For 5xx server errors
    """
    client = get_async_client(base_url)

    response = await client.request(
        method=method, url=path, headers=headers, params=params, json=json
    )

    if 200 <= response.status_code < 300:
        return response

    error_message = f"HTTP {response.status_code}"
    try:
        error_body = response.json()
        error_message = (
            error_body.get("error", {}).get("message")
            or error_body.get("message")
            or error_body.get("detail")
            or error_message
        )
    except Exception:
        error_text = response.text
        if error_text:
            error_message = f"HTTP {response.status_code}: {error_text}"

    if response.status_code == 400:
        raise ClientError(error_message, code=400)
    if response.status_code == 401:
        raise AuthenticationError(error_message)
    if response.status_code == 403:
        raise AuthorizationError(error_message)
    if response.status_code == 422:
        raise UnprocessableEntity(error_message)
    if 500 <= response.status_code < 600:
        raise ServiceError(error_message, code=response.status_code)

    # For any other 4xx errors, use ClientError
    if 400 <= response.status_code < 500:
        raise ClientError(error_message, code=response.status_code)
    # For any other non-2xx/3xx/4xx/5xx, use ServiceError as fallback
    raise ServiceError(error_message, code=response.status_code)
