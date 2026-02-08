import logging
from functools import lru_cache

import httpx
from httpx import Limits

logger = logging.getLogger(__name__)


@lru_cache
def get_async_client(base_url: str) -> httpx.AsyncClient:
    """Get a cached async client with generous connection pool limits.

    Args:
        base_url: The base URL for the client

    Returns:
        httpx.AsyncClient with configured limits and error handling
    """
    try:
        # Configure generous connection pool limits
        limits = Limits(
            max_keepalive_connections=100,  # Max connections to keep alive
            max_connections=200,  # Max total connections allowed
            keepalive_expiry=30,  # Seconds to keep connections alive
        )

        # Configure timeout settings
        timeout = httpx.Timeout(
            connect=10.0,  # Connection timeout
            read=30.0,  # Read timeout
            write=30.0,  # Write timeout
            pool=10.0,  # Pool timeout
        )

        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            limits=limits,
            # Enable HTTP/2 for better connection reuse
            http2=True,
            # Follow redirects
            follow_redirects=True,
        )

        logger.debug(
            f"Created async client for base_url: {base_url} with limits: {limits}"
        )
        return client

    except Exception as e:
        logger.error(
            f"Failed to create async client for {base_url}: {e}", exc_info=True
        )
        # Return a basic client as fallback
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=30,
        )
