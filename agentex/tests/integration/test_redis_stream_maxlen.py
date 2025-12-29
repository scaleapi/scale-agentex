"""
Integration test to verify Redis stream max length behavior.

This test validates whether the RedisStreamRepository enforces any
max length trimming on stream messages.
"""

import pytest

from tests.fixtures.repositories import create_redis_stream_repository

# Test configuration
NUM_MESSAGES = 10500  # Test beyond 10,000 to check for hidden limits
TEST_STREAM_TOPIC = "test:maxlen:verification"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_stream_no_maxlen_enforcement(base_redis_client):
    """
    Test that Redis streams do NOT enforce a max length.

    This verifies the current implementation in RedisStreamRepository.send_data()
    does not use MAXLEN parameter, meaning streams grow unbounded.
    """
    # Create repository using the existing factory
    repository = create_redis_stream_repository(base_redis_client)

    # Clean up any existing test stream
    await repository.cleanup_stream(TEST_STREAM_TOPIC)

    # Send messages through the actual API
    print(f"\nAdding {NUM_MESSAGES} messages via RedisStreamRepository.send_data()...")
    for i in range(NUM_MESSAGES):
        await repository.send_data(
            topic=TEST_STREAM_TOPIC, data={"index": i, "message": f"test_message_{i}"}
        )
        if (i + 1) % 1000 == 0:
            print(f"  Sent {i + 1} messages...")

    # Check stream length using underlying Redis client
    stream_length = await repository.redis.xlen(TEST_STREAM_TOPIC)

    print(f"\n{'=' * 50}")
    print("RESULTS:")
    print(f"{'=' * 50}")
    print(f"Messages sent:     {NUM_MESSAGES}")
    print(f"Stream length:     {stream_length}")
    print(f"Messages trimmed:  {NUM_MESSAGES - stream_length}")

    # Get stream info for details
    info = await repository.redis.xinfo_stream(TEST_STREAM_TOPIC)
    print("\nSTREAM INFO:")
    print(f"Length:            {info.get('length')}")
    print(f"First entry ID:    {info.get('first-entry', [b'N/A'])[0]}")
    print(f"Last entry ID:     {info.get('last-entry', [b'N/A'])[0]}")

    # Memory usage
    memory = await repository.redis.memory_usage(TEST_STREAM_TOPIC)
    print(f"Memory usage:      {memory} bytes ({memory / 1024:.2f} KB)")

    # Cleanup
    await repository.cleanup_stream(TEST_STREAM_TOPIC)

    # Assert no trimming occurred
    assert stream_length == NUM_MESSAGES, (
        f"Expected {NUM_MESSAGES} messages but found {stream_length}. "
        f"Redis may be enforcing a max length!"
    )

    print(f"\n✓ PASSED: No max length enforced - all {NUM_MESSAGES} messages retained")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_stream_info_after_messages(base_redis_client):
    """
    Test to gather detailed stream information after adding messages.

    This is useful for understanding Redis stream behavior and memory characteristics.
    """
    repository = create_redis_stream_repository(base_redis_client)
    topic = "test:stream:info"

    await repository.cleanup_stream(topic)

    # Add a smaller batch of messages
    message_count = 100
    for i in range(message_count):
        await repository.send_data(
            topic=topic,
            data={
                "index": i,
                "payload": "x" * 100,  # 100 byte payload
                "nested": {"key": f"value_{i}"},
            },
        )

    # Get comprehensive stream info
    info = await repository.redis.xinfo_stream(topic)
    length = await repository.redis.xlen(topic)
    memory = await repository.redis.memory_usage(topic)

    print(f"\n{'=' * 50}")
    print(f"STREAM ANALYSIS: {topic}")
    print(f"{'=' * 50}")
    print(f"Total messages:    {length}")
    print(f"Memory usage:      {memory} bytes")
    print(f"Bytes per message: {memory / length:.2f}")
    print(f"Radix tree keys:   {info.get('radix-tree-keys')}")
    print(f"Radix tree nodes:  {info.get('radix-tree-nodes')}")

    await repository.cleanup_stream(topic)

    assert length == message_count
