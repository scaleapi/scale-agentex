"""Per-account feature flag provider.

Queries egp-api-backend's ``GET /feature-flag/{id}`` endpoint with the
caller's identity headers. The endpoint evaluates the flag against the
account_id resolved from those headers and returns a ``FeatureFlag``
payload whose ``value`` field is a typed flag value (bool for ``boolean``
flags, etc.).

Falls back to disabled (``False``) on any error so a transient
egp-api-backend outage doesn't break the dual-write path — the flag-off
behavior is the safe legacy path.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends

from src.config.dependencies import DEnvironmentVariable
from src.config.environment_variables import EnvVarKeys
from src.utils.cached_httpx_client import get_async_client
from src.utils.logging import make_logger

logger = make_logger(__name__)


class FeatureFlagName(StrEnum):
    FGAC_TASKS = "fgac-tasks"
    FGAC_TASKS_DUAL_WRITE = "fgac-tasks-dual-write"
    FGAC_AGENT_API_KEYS_DUAL_WRITE = "fgac-agent-api-keys-dual-write"


class FeatureFlagProvider:
    """Per-account feature flag provider backed by egp-api-backend.

    Calls ``GET {EGP_API_BACKEND_URL}/feature-flag/{name}`` with the
    caller's identity headers. The endpoint evaluates the flag against the
    caller's account and returns a ``FeatureFlag`` with a ``value`` field.
    For boolean flags this method coerces the value to ``bool``.

    Returns ``False`` (flag off) when:
    - ``EGP_API_BACKEND_URL`` is not configured;
    - the caller's principal has no usable identity headers;
    - egp-api-backend returns a non-2xx response;
    - any network or parsing error occurs.

    Fail-closed-to-disabled is intentional: the legacy code path is the
    safe default if FGAC dual-write is unreachable.
    """

    def __init__(
        self,
        egp_api_backend_url: DEnvironmentVariable(EnvVarKeys.EGP_API_BACKEND_URL),
    ):
        self.egp_api_backend_url = egp_api_backend_url

    async def is_enabled(
        self,
        name: FeatureFlagName,
        *,
        principal_context: Any,
        account_id: str | None,
    ) -> bool:
        if not self.egp_api_backend_url:
            return False

        headers = self._principal_headers(principal_context, account_id)
        if not headers:
            return False

        url = f"{self.egp_api_backend_url.rstrip('/')}/feature-flag/{name.value}"
        try:
            client = get_async_client()
            response = await client.get(url, headers=headers)
        except Exception as exc:
            logger.warning(
                "Feature flag fetch failed; treating as disabled",
                extra={
                    "flag": name.value,
                    "account_id": account_id,
                    "error_type": type(exc).__name__,
                },
            )
            return False

        if response.status_code != 200:
            logger.warning(
                "Feature flag non-2xx response; treating as disabled",
                extra={
                    "flag": name.value,
                    "account_id": account_id,
                    "status_code": response.status_code,
                },
            )
            return False

        try:
            payload = response.json()
            value = payload.get("value")
        except Exception:
            logger.warning(
                "Feature flag response not JSON-parseable; treating as disabled",
                extra={"flag": name.value, "account_id": account_id},
            )
            return False

        return bool(value)

    @staticmethod
    def _principal_headers(
        principal_context: Any, account_id: str | None
    ) -> dict[str, str]:
        """Build identity headers from the caller's principal_context so
        egp-api-backend's ``REQUIRE_IDENTITY_AND_OPTIONAL_ACCOUNT`` policy
        admits the request.

        Returns ``{}`` when no usable identity is present — the caller
        should treat that as flag-off (the legacy path is safe).
        """
        if principal_context is None:
            return {}

        api_key = getattr(principal_context, "api_key", None)
        user_id = getattr(principal_context, "user_id", None)
        service_account_id = getattr(principal_context, "service_account_id", None)

        if not api_key and not user_id and not service_account_id:
            return {}

        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        if user_id:
            headers["x-user-id"] = user_id
        if service_account_id:
            headers["x-service-account-id"] = service_account_id
        if account_id:
            headers["x-selected-account-id"] = account_id
        return headers


DFeatureFlagProvider = Annotated[FeatureFlagProvider, Depends(FeatureFlagProvider)]
