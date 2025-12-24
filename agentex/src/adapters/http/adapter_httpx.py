import json
from collections.abc import AsyncIterator
from typing import Annotated, ClassVar, Literal

import httpx
from fastapi import Depends
from httpx import ConnectError, HTTPStatusError, Limits, Timeout, TimeoutException

from src.adapters.http.port import HttpPort
from src.config.dependencies import DEnvironmentVariables
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Global connection pool limits for better connection management
# Increased limits to handle streaming requests that hold connections longer
DEFAULT_LIMITS = Limits(
    max_keepalive_connections=1000,  # Max connections to keep alive (increased)
    max_connections=1000,  # Max total connections allowed (increased for streaming)
    keepalive_expiry=30,  # Seconds to keep connections alive
)


class HttpxGateway(HttpPort):
    # Class-level cached clients shared across all instances
    _regular_client: ClassVar[httpx.AsyncClient | None] = None
    _streaming_client: ClassVar[httpx.AsyncClient | None] = None
    _environment_variables: ClassVar[DEnvironmentVariables | None] = None

    def __init__(self, environment_variables: DEnvironmentVariables):
        """Initialize with environment variables for configuration."""
        if HttpxGateway._environment_variables is None:
            HttpxGateway._environment_variables = environment_variables

    @classmethod
    def _get_regular_client(cls) -> httpx.AsyncClient:
        """Get or create the shared regular HTTP client."""
        if cls._regular_client is None:
            env = cls._environment_variables
            timeout = Timeout(
                connect=env.HTTPX_CONNECT_TIMEOUT,
                read=env.HTTPX_READ_TIMEOUT,
                write=env.HTTPX_WRITE_TIMEOUT,
                pool=env.HTTPX_POOL_TIMEOUT,
            )
            cls._regular_client = httpx.AsyncClient(
                limits=DEFAULT_LIMITS,
                timeout=timeout,
                http2=True,  # Enable HTTP/2 for better connection reuse
                follow_redirects=True,
            )
            logger.info(
                f"Created shared regular httpx client (id: {id(cls._regular_client)})"
            )
        return cls._regular_client

    @classmethod
    def _get_streaming_client(cls) -> httpx.AsyncClient:
        """Get or create the shared streaming HTTP client."""
        if cls._streaming_client is None:
            env = cls._environment_variables
            # Use longer timeout for streaming
            streaming_timeout = Timeout(
                connect=env.HTTPX_CONNECT_TIMEOUT,
                read=env.HTTPX_STREAMING_READ_TIMEOUT,
                write=env.HTTPX_WRITE_TIMEOUT,
                pool=env.HTTPX_POOL_TIMEOUT,
            )
            cls._streaming_client = httpx.AsyncClient(
                limits=DEFAULT_LIMITS,
                timeout=streaming_timeout,
                http2=True,  # Enable HTTP/2 for better streaming
                follow_redirects=True,
            )
            logger.info(
                f"Created shared streaming httpx client (id: {id(cls._streaming_client)})"
            )
        return cls._streaming_client

    @classmethod
    async def close_clients(cls) -> None:
        """Close and cleanup the shared clients. Called during app shutdown for proper cleanup."""
        if cls._regular_client:
            await cls._regular_client.aclose()
            cls._regular_client = None
            logger.info("Closed shared regular httpx client")

        if cls._streaming_client:
            await cls._streaming_client.aclose()
            cls._streaming_client = None
            logger.info("Closed shared streaming httpx client")

    async def async_call(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        url: str,
        payload: dict | None = None,
        timeout: int | None = None,
        default_headers: dict | None = None,
    ) -> dict:
        """Make an async HTTP call using the cached client with connection pool."""
        # Get the shared client
        client = self._get_regular_client()

        try:
            logger.debug(f"Making {method} request to {url}")

            # Build request kwargs
            request_kwargs = {
                "method": method,
                "url": url,
                "json": payload,
                "headers": default_headers,
            }

            # Use custom timeout if provided
            if timeout is not None:
                request_kwargs["timeout"] = float(timeout)

            response = await client.request(**request_kwargs)
            response.raise_for_status()

            # Log successful response
            logger.debug(
                f"Successful {method} request to {url}, status: {response.status_code}"
            )
            return response.json()

        except HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} for {method} {url}: {e}",
                exc_info=True,
            )
            raise
        except ConnectError as e:
            logger.error(
                f"Connection error for {method} {url}: {e}. This might be a connection pool issue.",
                exc_info=True,
            )
            raise
        except TimeoutException as e:
            logger.error(f"Timeout error for {method} {url}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during {method} request to {url}: {e}", exc_info=True
            )
            raise

    async def stream_call(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        url: str,
        payload: dict | None = None,
        timeout: int | None = None,
        default_headers: dict | None = None,
    ) -> AsyncIterator[dict]:
        """Make a streaming HTTP call using the cached streaming client.

        Uses standard async with for proper cleanup. The real issue is likely
        elsewhere (e.g., CPU bound operations or memory accumulation).
        """
        # Get the shared streaming client
        client = self._get_streaming_client()

        if default_headers is None:
            default_headers = {}
        default_headers.update(
            {"Accept": "text/event-stream", "Content-Type": "application/json"}
        )

        try:
            logger.debug(f"Starting streaming {method} request to {url}")

            # Build stream kwargs
            stream_kwargs = {
                "method": method,
                "url": url,
                "json": payload,
                "headers": default_headers,
            }

            # Use custom timeout if provided
            if timeout is not None:
                stream_kwargs["timeout"] = float(timeout)

            async with client.stream(**stream_kwargs) as response:
                response.raise_for_status()
                logger.debug(
                    f"Streaming connection established to {url}, status: {response.status_code}"
                )

                async for line in response.aiter_lines():
                    if not line:  # Skip empty lines
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        # Log but don't fail on individual line parse errors
                        logger.warning(
                            f"Failed to parse SSE line (skipping): {line}, error: {e}"
                        )
                        continue

        except HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} for streaming {method} {url}: {e}",
                exc_info=True,
            )
            raise
        except ConnectError as e:
            logger.error(
                f"Connection error for streaming {method} {url}: {e}. This might be a connection pool issue.",
                exc_info=True,
            )
            raise
        except TimeoutException as e:
            logger.error(
                f"Timeout error for streaming {method} {url}: {e}", exc_info=True
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during streaming {method} request to {url}: {e}",
                exc_info=True,
            )
            raise

    def call(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        url: str,
        payload: dict | None = None,
        timeout: int | None = None,
        default_headers: dict | None = None,
    ) -> dict:
        """Make a synchronous HTTP call with improved connection pool management and error handling.

        Note: This method is not used in the codebase but is required by the HttpPort interface.
        Consider using async_call for better performance in async contexts.
        """
        env = self._environment_variables
        # Configure timeout
        if timeout is not None:
            httpx_timeout = Timeout(timeout=float(timeout))
        else:
            httpx_timeout = Timeout(
                connect=env.HTTPX_CONNECT_TIMEOUT,
                read=env.HTTPX_READ_TIMEOUT,
                write=env.HTTPX_WRITE_TIMEOUT,
                pool=env.HTTPX_POOL_TIMEOUT,
            )

        try:
            # Use a client with connection pool limits for sync calls
            with httpx.Client(
                limits=DEFAULT_LIMITS,
                timeout=httpx_timeout,
                http2=True,  # Enable HTTP/2
                follow_redirects=True,
            ) as client:
                logger.debug(f"Making sync {method} request to {url}")

                response = client.request(
                    method,
                    url,
                    json=payload,
                    headers=default_headers,
                )
                response.raise_for_status()

                # Log successful response
                logger.debug(
                    f"Successful sync {method} request to {url}, status: {response.status_code}"
                )
                return response.json()

        except HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} for sync {method} {url}: {e}",
                exc_info=True,
            )
            raise
        except ConnectError as e:
            logger.error(
                f"Connection error for sync {method} {url}: {e}. This might be a connection pool issue.",
                exc_info=True,
            )
            raise
        except TimeoutException as e:
            logger.error(f"Timeout error for sync {method} {url}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error during sync {method} request to {url}: {e}",
                exc_info=True,
            )
            raise


DHttpxGateway = Annotated[HttpxGateway, Depends(HttpxGateway)]
