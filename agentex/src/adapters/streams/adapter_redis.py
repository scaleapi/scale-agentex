import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import redis.asyncio as redis
from datadog import statsd
from fastapi import Depends
from src.adapters.streams.port import StreamRepository
from src.config.dependencies import DEnvironmentVariables, DRedisPool
from src.utils.logging import make_logger

logger = make_logger(__name__)


class RedisStreamRepository(StreamRepository):
    def __init__(
        self,
        environment_variables: DEnvironmentVariables,
        redis_pool: DRedisPool,
    ):
        # Use the singleton Redis connection pool from GlobalDependencies
        # This ensures all Redis operations share the same pool
        if redis_pool:
            self.redis = redis.Redis(connection_pool=redis_pool)
            logger.info("Using singleton Redis connection pool")
        else:
            # Fallback for cases where pool isn't available (e.g., tests)
            logger.warning("Redis pool not available, creating fallback connection")
            self.redis = redis.from_url(
                environment_variables.REDIS_URL, decode_responses=False
            )
        self.environment_variables = environment_variables

    async def send_data(self, topic: str, data: dict[str, Any]) -> str:
        """
        Send data to a Redis stream.

        Args:
            topic: The stream topic/name
            data: The data (will be JSON serialized)

        Returns:
            The message ID from Redis
        """
        try:
            # Simple JSON serialization
            data_json = json.dumps(data)

            logger.info(f"Publishing data to stream {topic}, data: {data_json}")

            # Add to Redis stream with a reasonable max length
            await self.send_redis_connection_metrics()
            message_id = await self.redis.xadd(
                name=topic,
                fields={"data": data_json},
            )
            await self.send_redis_connection_metrics()
            return message_id
        except Exception as e:
            logger.error(f"Error publishing data to Redis stream {topic}: {e}")
            raise

    async def send_redis_connection_metrics(self):
        try:
            info = await self.redis.info()
            env_value = self.environment_variables.ENVIRONMENT
            tags = [f"env:{env_value}"]

            def _send_redis_connection_metrics(self):
                # Send metrics directly - statsd is typically non-blocking
                statsd.gauge(
                    "redis.connections.current",
                    info.get("connected_clients", -1),
                    tags=tags,
                )
                statsd.gauge(
                    "redis.connections.total",
                    info.get("total_connections_received", -1),
                    tags=tags,
                )
                statsd.gauge(
                    "redis.connections.rejected",
                    info.get("rejected_connections", -1),
                    tags=tags,
                )
                statsd.gauge(
                    "redis.connections.evicted",
                    info.get("evicted_clients", -1),
                    tags=tags,
                )
                statsd.gauge(
                    "redis.connections.expired",
                    info.get("expired_clients", -1),
                    tags=tags,
                )
                statsd.gauge(
                    "redis.connections.blocked",
                    info.get("blocked_clients", -1),
                    tags=tags,
                )

            await asyncio.to_thread(_send_redis_connection_metrics, self)
        except Exception as e:
            logger.error(f"Failed to send metrics: {e}", exc_info=e)

    async def read_messages(
        self, topic: str, last_id: str, timeout_ms: int = 2000, count: int = 10
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        logger.info(f"Reading messages from Redis stream {topic}, last_id: {last_id}")
        """
        Read messages from a Redis stream and yield them one by one.

        Args:
            topic: The stream topic to read from
            last_id: Where to start reading from:
                    "$" = only new messages
                    "0" = all messages from the beginning
                    "<id>" = messages after the specified ID
            timeout_ms: How long to block waiting for new messages (in milliseconds)
            count: Maximum number of messages to read

        Yields:
            Tuples of (message_id, data) for each message
        """

        # logger.info(f"Reading messages from Redis stream {topic}, last_id: {last_id}")
        try:
            # Read messages with the specified block time
            streams = {topic: last_id}
            await self.send_redis_connection_metrics()

            response = await self.redis.xread(
                streams=streams, count=count, block=timeout_ms
            )

            if response:
                # # Uncomment to debug
                # logger.info(f"Received response from Redis stream {topic}: {response}")

                for _stream_name, messages in response:
                    for message_id, fields in messages:
                        # # Uncomment to debug
                        # logger.info(f"Received message from Redis stream {topic}: {message_id}, fields: {fields}")

                        # Extract and parse the JSON data
                        if b"data" in fields:
                            try:
                                data_str = fields[b"data"].decode("utf-8")
                                data = json.loads(data_str)
                                # Yield each message with its ID
                                yield message_id, data
                            except Exception as e:
                                logger.warning(
                                    f"Failed to parse data from Redis stream: {e}"
                                )

        except Exception as e:
            logger.error(f"Error reading from Redis stream {topic}: {e}")
            raise

    async def cleanup_stream(self, topic: str) -> None:
        """
        Clean up a Redis stream.

        Args:
            topic: The stream topic to clean up
        """
        try:
            await self.redis.delete(topic)
            await self.send_redis_connection_metrics()
            logger.info(f"Cleaned up Redis stream: {topic}")
        except Exception as e:
            logger.error(f"Error cleaning up Redis stream {topic}: {e}")
            raise


DRedisStreamRepository = Annotated[
    RedisStreamRepository, Depends(RedisStreamRepository)
]
