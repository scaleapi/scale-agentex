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
