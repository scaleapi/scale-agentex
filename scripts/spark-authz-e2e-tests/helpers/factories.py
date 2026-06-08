"""Unique-name factories. Test runs collide on stale state otherwise."""

import time
import uuid


def unique_agent_name(prefix: str = "e2e-agent") -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def unique_api_key_name(prefix: str = "e2e-api-key") -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def unique_task_name(prefix: str = "e2e-task") -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
