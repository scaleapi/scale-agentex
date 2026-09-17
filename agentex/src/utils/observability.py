"""Optional observability callbacks, loaded before application dependencies."""

from __future__ import annotations

import importlib
import logging
import os
from types import ModuleType
from typing import TYPE_CHECKING
from weakref import WeakSet

if TYPE_CHECKING:
    from fastapi import FastAPI

_adapter: ModuleType | None = None
_logging_initialized = False
_logging_prepared = False
_logging_managed = False
_shutdown_called = False
_configured_apps: WeakSet[FastAPI] = WeakSet()


def _report_failure(stage: str) -> None:
    logging.getLogger(__name__).warning(
        "Optional observability adapter failed during %s", stage, exc_info=True
    )
    if os.environ.get("CI", "").lower() in {"true", "1", "yes"}:
        raise RuntimeError(f"Observability adapter failed during {stage}")


def initialize_logging() -> None:
    """Prepare logging once, before modules create their application loggers."""
    global _adapter, _logging_initialized, _logging_managed, _logging_prepared
    if _logging_initialized:
        return
    _logging_initialized = True
    module_name = os.environ.get("AGENTEX_OBSERVABILITY_MODULE", "").strip()
    if not module_name:
        return
    try:
        _adapter = importlib.import_module(module_name)
        managed = _adapter.initialize_logging()
        if not isinstance(managed, bool):
            raise TypeError("initialize_logging() must return a bool")
        _logging_managed = managed
        _logging_prepared = True
    except Exception:
        _report_failure("logging initialization")


def is_logging_managed() -> bool:
    """Whether the adapter owns application logging handlers and formatting."""
    return _logging_managed


def configure_app(app: FastAPI) -> None:
    """Configure an app once, after its routes and middleware are registered."""
    if _adapter is None or not _logging_prepared or app in _configured_apps:
        return
    _configured_apps.add(app)
    try:
        from src.utils.otel_metrics import init_otel_metrics

        init_otel_metrics()
        _adapter.configure_app(app)
    except Exception:
        _report_failure("app configuration")


def shutdown() -> None:
    """Release adapter-owned resources once; the caller runs this off-loop."""
    global _shutdown_called
    if _adapter is None or _shutdown_called:
        return
    _shutdown_called = True
    try:
        _adapter.shutdown()
    except Exception:
        _report_failure("shutdown")
