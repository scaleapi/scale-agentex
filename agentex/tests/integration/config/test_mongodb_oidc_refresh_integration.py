"""Integration tests for the MongoDB client-refresh swap against a real Mongo.

The unit tests mock the client; these prove the build-validate-swap-drain works
end-to-end against a live MongoDB container: data written before the swap is still
readable after it, the post-swap client is fully functional, and the superseded
client is drained and closed. (The container doesn't speak GCP OIDC, so the OIDC
gate is forced on to exercise the swap path itself.)
"""

from unittest.mock import AsyncMock

import pytest
from src.config.dependencies import GlobalDependencies, Singleton


@pytest.fixture
def deps(mongodb_connection_string):
    """Fresh GlobalDependencies wired to the test Mongo container."""
    Singleton._instances.pop(GlobalDependencies, None)
    instance = GlobalDependencies()
    instance.environment_variables = instance.environment_variables.model_copy(
        update={
            "MONGODB_URI": mongodb_connection_string,
            "MONGODB_DATABASE_NAME": "agentex_oidc_refresh_test",
        }
    )
    instance.mongodb_client = instance._build_mongodb_client(mongodb_connection_string)
    instance.mongodb_database = instance.mongodb_client["agentex_oidc_refresh_test"]
    yield instance
    Singleton._instances.pop(GlobalDependencies, None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_refresh_preserves_data_and_drains_old_client(deps, monkeypatch):
    # Treat the container URI as OIDC so the refresh path actually runs, and
    # collapse the drain delay so the close completes within the test.
    monkeypatch.setattr(deps, "_mongodb_uses_oidc", lambda: True)
    original_close_after_delay = deps._close_mongodb_client_after_delay

    async def fast_close(client, delay=0.0):
        await original_close_after_delay(client, delay=0.0)

    monkeypatch.setattr(deps, "_close_mongodb_client_after_delay", fast_close)

    collection = "docs"
    await deps.mongodb_database[collection].insert_one({"_id": "before", "n": 1})

    old_client = deps.mongodb_client
    old_client.close = AsyncMock(wraps=old_client.close)

    await deps.refresh_mongodb_client()

    # A genuinely new client is now installed.
    assert deps.mongodb_client is not old_client

    # The new client can write, and reads the doc written before the swap.
    await deps.mongodb_database[collection].insert_one({"_id": "after", "n": 2})
    ids = {
        doc["_id"]
        async for doc in deps.mongodb_database[collection].find({}, {"_id": 1})
    }
    assert ids == {"before", "after"}

    # The superseded client is drained and closed.
    for task in list(deps._mongodb_close_tasks):
        await task
    old_client.close.assert_awaited_once()

    await deps.mongodb_client.drop_database("agentex_oidc_refresh_test")
    await deps.mongodb_client.close()
