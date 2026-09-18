"""Select ordinary pools and skip native collectors in adapter mode."""

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool
from src.config import dependencies, environment_variables
from src.utils.db_metrics import InstrumentedAsyncAdaptedQueuePool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("managed", [False, True])
async def test_database_setup_uses_selected_instrumentation(monkeypatch, managed):
    monkeypatch.setattr(environment_variables, "refreshed_environment_variables", None)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.delenv("READ_ONLY_DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(dependencies, "is_managed", lambda: managed)

    async def no_temporal(_self):
        return None

    def unavailable_mongo(*args, **kwargs):
        raise ConnectionError("MongoDB is outside this test")

    monkeypatch.setattr(
        dependencies.GlobalDependencies, "create_temporal_client", no_temporal
    )
    monkeypatch.setattr(dependencies, "AsyncMongoClient", unavailable_mongo)
    instance = type.__call__(dependencies.GlobalDependencies)
    await instance.load()
    engines = [
        instance.database_async_read_write_engine,
        instance.database_async_middleware_read_write_engine,
        instance.database_async_read_only_engine,
    ]
    try:
        expected = (
            AsyncAdaptedQueuePool if managed else InstrumentedAsyncAdaptedQueuePool
        )
        assert all(type(engine.pool) is expected for engine in engines)
        assert (instance.postgres_metrics_collector is None) is managed
    finally:
        for engine in engines:
            await engine.dispose()
        await instance.httpx_client.aclose()
