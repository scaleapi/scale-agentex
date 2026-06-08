"""Cleanup utilities for Spark AuthZ E2E tests.

Provides a context-manager style cleanup tracker so tests can register
resources for teardown. Cleanup runs in LIFO order and never raises —
failures are logged but don't mask test results.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CleanupAction:
    description: str
    fn: Callable[[], None]


class CleanupTracker:
    """Register cleanup actions that execute in LIFO order on close."""

    def __init__(self) -> None:
        self._actions: list[CleanupAction] = []

    def add(self, description: str, fn: Callable[[], None]) -> None:
        self._actions.append(CleanupAction(description=description, fn=fn))

    def execute(self) -> None:
        for action in reversed(self._actions):
            try:
                action.fn()
                logger.debug("Cleanup OK: %s", action.description)
            except Exception:
                logger.warning("Cleanup failed: %s", action.description, exc_info=True)
        self._actions.clear()
