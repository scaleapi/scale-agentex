"""Select an optional telemetry adapter once per process."""

from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Sequence
from functools import cache
from types import ModuleType
from typing import TYPE_CHECKING
from weakref import WeakSet

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.metrics import Meter
    from temporalio.client import Interceptor

_configured_apps: WeakSet[FastAPI] = WeakSet()
_worker_initialized = False
_shutdown_called = False


@cache
def _adapter() -> ModuleType | None:
    module_name = os.environ.get("AGENTEX_OBSERVABILITY_MODULE", "").strip()
    if not module_name:
        return None
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name or module_name.startswith(f"{exc.name}."):
            return None
        raise


def uses_observability_adapter() -> bool:
    """Whether an installed adapter replaces built-in instrumentation."""
    return _adapter() is not None


def initialize(app: FastAPI) -> None:
    """Initialize after routes and middleware, before serving requests."""
    adapter = _adapter()
    if adapter is None or app in _configured_apps:
        return
    try:
        adapter.initialize(app)
    except Exception:
        try:
            shutdown()
        except Exception:
            logging.getLogger(__name__).exception("Observability cleanup failed")
        raise
    _configured_apps.add(app)


def initialize_worker() -> None:
    """Initialize once before importing worker dependencies and clients."""
    global _worker_initialized
    adapter = _adapter()
    if adapter is None or _worker_initialized:
        return
    try:
        adapter.initialize_worker()
        from src.utils.logging import SensitiveDataFilter

        # Logger filters survive replacement of the adapter's output handlers.
        for name in ("temporalio.workflow", "temporalio.activity"):
            logger = logging.getLogger(name)
            if not any(
                isinstance(item, SensitiveDataFilter) for item in logger.filters
            ):
                logger.addFilter(SensitiveDataFilter())
    except Exception:
        try:
            shutdown()
        except Exception:
            logging.getLogger(__name__).exception("Observability cleanup failed")
        raise
    _worker_initialized = True


def temporal_client_interceptors() -> Sequence[Interceptor]:
    """Client interceptors also instrument workers using that client."""
    adapter = _adapter()
    callback = getattr(adapter, "temporal_client_interceptors", None)
    return callback() if callback is not None else ()


def get_meter(name: str, version: str) -> Meter | None:
    """Use an adapter meter without creating a second provider."""
    adapter = _adapter()
    callback = getattr(adapter, "get_meter", None)
    return callback(name, version) if callback is not None else None


def shutdown() -> None:
    """Flush the adapter once; call off the event loop."""
    global _shutdown_called
    adapter = _adapter()
    if adapter is None or _shutdown_called:
        return
    _shutdown_called = True
    adapter.shutdown()
