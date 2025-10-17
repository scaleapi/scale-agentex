from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from src.utils.logging import make_logger

logger = make_logger(__name__)

"""
Authentication caching module for middleware.

Provides async-safe caching for:
1. Agent identity/API key verification
2. Auth gateway responses
3. Headers-based authentication

Uses in-memory caching with TTL support and optional Redis backend.
Thread-safe and async-safe implementation using asyncio locks.
"""


class AsyncTTLCache:
    """Async-safe TTL cache implementation using OrderedDict with asyncio locks."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize async-safe TTL cache.

        Args:
            max_size: Maximum number of entries in the cache
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get value from cache if it exists and hasn't expired."""
        async with self._lock:
            if key not in self.cache:
                return None

            value, timestamp = self.cache[key]

            # Check if entry has expired
            if time.time() - timestamp > self.ttl_seconds:
                del self.cache[key]
                return None

            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        async with self._lock:
            # Remove oldest entry if cache is full
            if len(self.cache) >= self.max_size and key not in self.cache:
                self.cache.popitem(last=False)

            self.cache[key] = (value, time.time())
            self.cache.move_to_end(key)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self.cache.clear()

    async def remove_expired(self) -> None:
        """Remove all expired entries from cache."""
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key
                for key, (_, timestamp) in self.cache.items()
                if current_time - timestamp > self.ttl_seconds
            ]
            for key in expired_keys:
                del self.cache[key]

    def size(self) -> int:
        """Get current cache size (non-async for stats)."""
        # This is safe to read without lock for approximate size
        return len(self.cache)


class AuthenticationCache:
    """
    Async-safe caching layer for authentication and authorization middleware.

    Provides caching for:
    - Agent identity verification
    - Agent API key verification
    - Auth gateway responses
    - Authorization checks
    """

    def __init__(
        self,
        agent_cache_ttl: int = 300,  # 5 minutes
        auth_gateway_cache_ttl: int = 60,  # 1 minute
        authorization_cache_ttl: int = 300,  # 5 minutes
        max_cache_size: int = 1000,
    ):
        """
        Initialize async-safe authentication and authorization cache.

        Args:
            agent_cache_ttl: TTL for agent identity/API key cache in seconds
            auth_gateway_cache_ttl: TTL for auth gateway cache in seconds
            authorization_cache_ttl: TTL for authorization checks in seconds
            max_cache_size: Maximum number of entries per cache
        """
        # Separate async-safe caches for different authentication types
        self.agent_identity_cache = AsyncTTLCache(max_cache_size, agent_cache_ttl)
        self.agent_api_key_cache = AsyncTTLCache(max_cache_size, agent_cache_ttl)
        self.auth_gateway_cache = AsyncTTLCache(max_cache_size, auth_gateway_cache_ttl)
        self.authorization_check_cache = AsyncTTLCache(
            max_cache_size, authorization_cache_ttl
        )

        logger.info(
            "Async-safe authentication cache initialized with TTLs: "
            f"agent={agent_cache_ttl}s, gateway={auth_gateway_cache_ttl}s, "
            f"authorization={authorization_cache_ttl}s"
        )

    @staticmethod
    def _hash_dict(data: dict) -> str:
        """
        Create a hash key from a dictionary.

        Sorts keys to ensure consistent hashing regardless of key order.
        """
        # Sort the dictionary by keys and convert to JSON string
        sorted_json = json.dumps(data, sort_keys=True)
        # Create SHA256 hash of the JSON string
        return hashlib.sha256(sorted_json.encode()).hexdigest()

    @staticmethod
    def _create_headers_cache_key(headers: dict[str, str]) -> str:
        """
        Create a cache key from request headers.

        Only includes relevant authentication headers to avoid cache pollution.
        """
        # Extract only authentication-relevant headers
        auth_headers = {}
        for key, value in headers.items():
            lower_key = key.lower()
            # Include authorization, cookie, and custom auth headers
            if any(
                h in lower_key
                for h in [
                    "authorization",
                    "cookie",
                    "x-auth",
                    "x-api-key",
                    "x-session",
                    "x-selected-account-id",
                    "x-user-id",
                ]
            ):
                auth_headers[lower_key] = value

        return AuthenticationCache._hash_dict(auth_headers)

    # Agent Identity Cache Methods (Async)

    async def get_agent_identity(self, agent_id: str) -> str | None:
        """Get cached agent identity verification result."""
        result = await self.agent_identity_cache.get(f"agent_id:{agent_id}")
        if result is not None:
            logger.debug(f"Cache hit for agent identity: {agent_id}")
        return result

    async def set_agent_identity(
        self, agent_id: str, verified_agent_id: str | None
    ) -> None:
        """Cache agent identity verification result."""
        await self.agent_identity_cache.set(f"agent_id:{agent_id}", verified_agent_id)
        logger.debug(f"Cached agent identity verification: {agent_id}")

    # Agent API Key Cache Methods (Async)

    async def get_agent_api_key(self, api_key: str) -> str | None:
        """Get cached agent ID for API key."""
        # Hash the API key for security
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await self.agent_api_key_cache.get(f"api_key:{key_hash}")
        if result is not None:
            logger.debug("Cache hit for agent API key")
        return result

    async def set_agent_api_key(self, api_key: str, agent_id: str | None) -> None:
        """Cache agent API key verification result."""
        # Hash the API key for security
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        await self.agent_api_key_cache.set(f"api_key:{key_hash}", agent_id)
        logger.debug("Cached agent API key verification")

    # Auth Gateway Cache Methods (Async)

    async def get_auth_gateway_response(self, headers: dict[str, str]) -> Any | None:
        """Get cached auth gateway response for headers."""
        cache_key = self._create_headers_cache_key(headers)
        result = await self.auth_gateway_cache.get(f"gateway:{cache_key}")
        if result is not None:
            logger.debug("Cache hit for auth gateway")
        return result

    async def set_auth_gateway_response(
        self, headers: dict[str, str], principal_context: Any
    ) -> None:
        """Cache auth gateway response."""
        cache_key = self._create_headers_cache_key(headers)
        await self.auth_gateway_cache.set(f"gateway:{cache_key}", principal_context)
        logger.debug("Cached auth gateway response")

    # Authorization Check Cache Methods (Async)

    @staticmethod
    def _create_authorization_cache_key(
        resource_type: str,
        resource_selector: str,
        operation: str,
        principal_context: Any,
    ) -> str:
        """
        Create a cache key for authorization checks.

        Combines resource info, operation, and principal context into a unique key.
        """
        # Extract relevant fields from principal context for cache key
        principal_key_data = {}
        if principal_context:
            # Handle different types of principal context
            if hasattr(principal_context, "__dict__"):
                # If it's an object with attributes
                context_dict = principal_context.__dict__
            elif isinstance(principal_context, dict):
                context_dict = principal_context
            else:
                # Convert to string if it's a simple type
                context_dict = {"value": str(principal_context)}

            # Extract key fields that identify the principal
            for key in ["user_id", "account_id", "agent_id", "id", "sub", "email"]:
                if key in context_dict:
                    principal_key_data[key] = context_dict[key]

            # If no identifying fields found, hash the entire context
            if not principal_key_data:
                principal_key_data = {
                    "context_hash": AuthenticationCache._hash_dict(context_dict)
                }

        # Create the cache key components
        cache_data = {
            "resource_type": resource_type,
            "resource_selector": resource_selector,
            "operation": operation,
            "principal": principal_key_data,
        }

        return f"authz:{AuthenticationCache._hash_dict(cache_data)}"

    async def get_authorization_check(
        self,
        resource_type: str,
        resource_selector: str,
        operation: str,
        principal_context: Any,
    ) -> bool | None:
        """Get cached authorization check result."""
        cache_key = self._create_authorization_cache_key(
            resource_type, resource_selector, operation, principal_context
        )
        result = await self.authorization_check_cache.get(cache_key)
        if result is not None:
            logger.info(
                f"Cache hit for authorization check: {resource_type}:{resource_selector} "
                f"operation={operation}"
            )
        return result

    async def set_authorization_check(
        self,
        resource_type: str,
        resource_selector: str,
        operation: str,
        principal_context: Any,
        allowed: bool,
    ) -> None:
        """Cache authorization check result."""
        cache_key = self._create_authorization_cache_key(
            resource_type, resource_selector, operation, principal_context
        )
        await self.authorization_check_cache.set(cache_key, allowed)
        logger.debug(
            f"Cached authorization check: {resource_type}:{resource_selector} "
            f"operation={operation} allowed={allowed}"
        )

    # Maintenance Methods (Async)

    async def clear_all(self) -> None:
        """Clear all caches."""
        await self.agent_identity_cache.clear()
        await self.agent_api_key_cache.clear()
        await self.auth_gateway_cache.clear()
        await self.authorization_check_cache.clear()
        logger.info("All authentication and authorization caches cleared")

    async def cleanup_expired(self) -> None:
        """Remove expired entries from all caches."""
        await self.agent_identity_cache.remove_expired()
        await self.agent_api_key_cache.remove_expired()
        await self.auth_gateway_cache.remove_expired()
        await self.authorization_check_cache.remove_expired()
        logger.debug("Cleaned up expired cache entries")

    def get_cache_stats(self) -> dict:
        """Get statistics about cache usage (non-async for monitoring)."""
        return {
            "agent_identity_cache_size": self.agent_identity_cache.size(),
            "agent_api_key_cache_size": self.agent_api_key_cache.size(),
            "auth_gateway_cache_size": self.auth_gateway_cache.size(),
            "authorization_check_cache_size": self.authorization_check_cache.size(),
        }


# Global cache instance with async-safe initialization
_auth_cache: AuthenticationCache | None = None
_auth_cache_lock = asyncio.Lock()


async def get_auth_cache() -> AuthenticationCache:
    """Get or create the global authentication cache instance (async-safe)."""
    global _auth_cache

    # Fast path: cache already exists
    if _auth_cache is not None:
        return _auth_cache

    # Slow path: need to create cache (with lock for safety)
    async with _auth_cache_lock:
        # Double-check pattern to avoid race conditions
        if _auth_cache is None:
            _auth_cache = AuthenticationCache()
            logger.info("Global authentication cache instance created")
        return _auth_cache


async def reset_auth_cache() -> None:
    """Reset the global authentication cache instance (async-safe)."""
    global _auth_cache

    async with _auth_cache_lock:
        if _auth_cache is not None:
            await _auth_cache.clear_all()
        _auth_cache = None
        logger.info("Global authentication cache instance reset")


# Backwards compatibility: synchronous wrapper for legacy code
def get_auth_cache_sync() -> AuthenticationCache:
    """
    Get the auth cache synchronously.
    WARNING: This creates a new cache if none exists.
    Prefer async get_auth_cache() in async contexts.
    """
    global _auth_cache
    if _auth_cache is None:
        _auth_cache = AuthenticationCache()
    return _auth_cache
