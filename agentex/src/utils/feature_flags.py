import os
from enum import StrEnum
from typing import Annotated

from fastapi import Depends


class FeatureFlagName(StrEnum):
    FGAC_TASKS = "fgac-tasks"
    FGAC_TASKS_DUAL_WRITE = "fgac-tasks-dual-write"
    FGAC_AGENT_API_KEYS_DUAL_WRITE = "fgac-agent-api-keys-dual-write"


class FeatureFlagProvider:
    """Per-account feature flag provider.

    v1: env-var allowlist (per-account, comma-separated). The env var name is
    derived from the flag name, e.g. ``FGAC_AGENT_API_KEYS_DUAL_WRITE_ACCOUNTS``.
    A follow-up will swap this for LaunchDarkly with an account_id context.
    """

    def is_enabled(self, name: FeatureFlagName, account_id: str | None) -> bool:
        if not account_id:
            return False
        env_key = f"{name.value.upper().replace('-', '_')}_ACCOUNTS"
        allowed = os.environ.get(env_key, "")
        return account_id in {a.strip() for a in allowed.split(",") if a.strip()}


DFeatureFlagProvider = Annotated[FeatureFlagProvider, Depends(FeatureFlagProvider)]
