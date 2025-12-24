"""
OpenTelemetry instrumentation for SQLAlchemy engines.
"""

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import AsyncEngine

from src.utils.logging import make_logger

logger = make_logger(__name__)

_instrumented_engines: set[int] = set()


def instrument_engine(
    engine: AsyncEngine | None,
    engine_name: str = "default",
) -> None:
    """
    Instrument a SQLAlchemy async engine with OpenTelemetry.

    For async engines, we instrument the underlying sync_engine since
    SQLAlchemyInstrumentor works at the sync engine level.

    Args:
        engine: The async SQLAlchemy engine to instrument
        engine_name: A name identifier for logging
    """
    if engine is None:
        logger.warning(f"Cannot instrument {engine_name}: engine is None")
        return

    engine_id = id(engine)
    if engine_id in _instrumented_engines:
        logger.debug(f"Engine {engine_name} already instrumented")
        return

    try:
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
        )
        _instrumented_engines.add(engine_id)
        logger.info(
            f"Instrumented SQLAlchemy engine '{engine_name}' with OpenTelemetry"
        )
    except Exception as e:
        logger.error(f"Failed to instrument SQLAlchemy engine '{engine_name}': {e}")


def uninstrument_all() -> None:
    """Remove instrumentation from all engines."""
    try:
        SQLAlchemyInstrumentor().uninstrument()
        _instrumented_engines.clear()
        logger.info("Uninstrumented all SQLAlchemy engines")
    except Exception as e:
        logger.error(f"Failed to uninstrument SQLAlchemy engines: {e}")
