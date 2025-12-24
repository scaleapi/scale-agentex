"""
Cache-Control header utilities for API endpoints.

Usage:
    @router.get("/items/{id}")
    @cacheable(max_age=60)
    async def get_item(id: str, response: Response) -> Item:
        ...

The decorator adds Cache-Control headers to responses. The endpoint must
include a `response: Response` parameter for the headers to be set.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import Response

P = ParamSpec("P")
T = TypeVar("T")


def cacheable(
    max_age: int = 60,
    private: bool = True,
    stale_while_revalidate: int | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to add Cache-Control headers to GET endpoint responses.

    Args:
        max_age: Maximum time in seconds the response can be cached (default: 60)
        private: If True, response is only cacheable by the client, not shared caches (default: True)
        stale_while_revalidate: Optional time in seconds to serve stale content while revalidating

    Example:
        @router.get("/agents/{id}")
        @cacheable(max_age=300)  # Cache for 5 minutes
        async def get_agent(id: str, response: Response) -> Agent:
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Get the response object from kwargs
            response: Response | None = kwargs.get("response")

            # Call the original function
            result = await func(*args, **kwargs)

            # Set Cache-Control header if response is available
            if response is not None:
                cache_control = (
                    f"{'private' if private else 'public'}, max-age={max_age}"
                )
                if stale_while_revalidate is not None:
                    cache_control += (
                        f", stale-while-revalidate={stale_while_revalidate}"
                    )
                response.headers["Cache-Control"] = cache_control

            return result

        return wrapper

    return decorator
