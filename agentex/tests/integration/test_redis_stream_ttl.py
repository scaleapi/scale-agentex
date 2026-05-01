import pytest


@pytest.mark.asyncio
@pytest.mark.integration
class TestRedisStreamTTL:
    """Integration tests for the sliding TTL on Redis stream keys."""

    async def test_send_data_sets_ttl_on_stream_key(self, isolated_repositories):
        """After send_data, the stream key has a TTL approximately equal to REDIS_STREAM_TTL_SECONDS."""
        repo = isolated_repositories["redis_stream_repository"]
        topic = "test:stream:ttl:basic"

        await repo.send_data(topic, {"hello": "world"})

        ttl = await repo.redis.ttl(topic)
        # ttl returns seconds remaining; -1 = no TTL, -2 = key missing.
        # We expect it close to the configured 3600 (allow generous slack for test scheduling).
        assert ttl > 0, f"Expected positive TTL, got {ttl}"
        assert ttl <= 3600, f"Expected TTL <= 3600, got {ttl}"
        assert (
            ttl >= 3590
        ), f"Expected TTL >= 3590 (within 10s of configured), got {ttl}"

        # Cleanup
        await repo.redis.delete(topic)

    async def test_send_data_skips_ttl_when_disabled(self, isolated_repositories):
        """With REDIS_STREAM_TTL_SECONDS=0, no TTL is set on the stream key."""
        repo = isolated_repositories["redis_stream_repository"]
        repo.environment_variables.REDIS_STREAM_TTL_SECONDS = 0
        topic = "test:stream:ttl:disabled"

        try:
            await repo.send_data(topic, {"hello": "world"})

            ttl = await repo.redis.ttl(topic)
            # -1 means key exists but has no TTL.
            assert ttl == -1, f"Expected no TTL (-1), got {ttl}"
        finally:
            # Restore default + cleanup so other tests aren't affected.
            repo.environment_variables.REDIS_STREAM_TTL_SECONDS = 3600
            await repo.redis.delete(topic)

    async def test_send_data_still_applies_maxlen(self, isolated_repositories):
        """Stream length stays bounded near MAXLEN after many writes."""
        repo = isolated_repositories["redis_stream_repository"]
        # Tighten MAXLEN for this test so we can verify trimming without 10k writes.
        repo.environment_variables.REDIS_STREAM_MAXLEN = 50
        topic = "test:stream:ttl:maxlen"

        try:
            for i in range(200):
                await repo.send_data(topic, {"i": i})

            length = await repo.redis.xlen(topic)
            # `approximate=True` (XADD ~) lets length exceed MAXLEN slightly,
            # but should be in the same order of magnitude (well under 200).
            assert length <= 100, f"Expected length <= 100 with MAXLEN=50, got {length}"
        finally:
            repo.environment_variables.REDIS_STREAM_MAXLEN = 10000
            await repo.redis.delete(topic)
