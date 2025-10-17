from functools import lru_cache
import httpx


@lru_cache()
def get_async_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=5,
    )
