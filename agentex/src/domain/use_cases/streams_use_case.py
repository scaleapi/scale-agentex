import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from pydantic import ValidationError

from src.adapters.streams.adapter_redis import DRedisStreamRepository
from src.api.schemas.task_stream_events import TaskStreamEvent
from src.config.dependencies import DEnvironmentVariables
from src.domain.entities.task_stream_events import (
    TaskStreamConnectedEventEntity,
    TaskStreamErrorEventEntity,
    TaskStreamEventEntity,
    convert_task_stream_event_to_entity,
)
from src.domain.services.task_service import DAgentTaskService
from src.utils.logging import make_logger
from src.utils.stream_topics import get_task_event_stream_topic

logger = make_logger(__name__)


class StreamsUseCase:
    def __init__(
        self,
        stream_repository: DRedisStreamRepository,
        task_service: DAgentTaskService,
        environment_variables: DEnvironmentVariables,
    ):
        self.stream_repository = stream_repository
        self.task_service = task_service
        self.environment_variables = environment_variables

    async def read_messages(
        self, topic: str, last_id: str = "$", timeout_ms: int = 2000, count: int = 10
    ) -> AsyncIterator[tuple[str, TaskStreamEventEntity]]:
        """
        Read messages from a stream and yield them one by one.

        This method gives the application control over the event loop
        while still providing a convenient generator interface.

        Args:
            topic: The topic to read from
            last_id: The ID to start reading from
                     "0" means from beginning
                     "$" means only new messages
            timeout_ms: How long to wait for new messages (milliseconds)
            count: Maximum number of messages to read

        Yields:
            Tuples of (message_id, event_data) for each message
        """
        # logger.info(f"Reading messages from stream topic: {topic}, from last_id: {last_id}")

        # Pass through the generator from the repository
        async for message_id, object in self.stream_repository.read_messages(
            topic=topic, last_id=last_id, timeout_ms=timeout_ms, count=count
        ):
            try:
                yield (
                    message_id,
                    convert_task_stream_event_to_entity(
                        TaskStreamEvent.model_validate(object)
                    ),
                )
            except ValidationError as e:
                logger.warning(f"Failed to validate stream event data: {e}")

    async def cleanup_stream(self, topic: str) -> None:
        """
        Cleanup resources associated with a stream when it ends.
        """
        logger.info(f"Cleaning up stream {topic}")
        try:
            # Add any cleanup logic here, such as:
            # - Removing stream from active streams list
            # - Closing any associated resources
            # - Notifying other parts of the system
            await self.stream_repository.cleanup_stream(topic)
        except Exception as e:
            logger.error(f"Error cleaning up stream {topic}: {e}")
            raise

    async def stream_task_events(
        self,
        task_id: str | None = None,
        task_name: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Async generator for streaming task message updates as SSE data strings.
        Sends keepalive pings to maintain long-lived connections.
        """
        task_id = task_id
        if not task_id:
            if not task_name:
                raise ValueError("Either task_id or task_name must be provided")

            task = await self.task_service.get_task(name=task_name)
            task_id = task.id

        stream_topic = get_task_event_stream_topic(task_id=task_id)
        # Snapshot the read cursor BEFORE yielding "connected". "connected" is
        # the client's cue to send its message, which makes the agent start
        # XADD-ing deltas. Snapshotting after the yield lets a congested relay
        # fall behind far enough that those deltas land before the snapshot and
        # are never read. Snapshotting first resolves to "0-0" (stream is empty
        # until the client sends), so we read from the beginning.
        last_id = await self.stream_repository.get_stream_tail_id(stream_topic)
        # Send initial connection data
        yield f"data: {TaskStreamConnectedEventEntity(type='connected', taskId=task_id).model_dump_json()}\n\n"
        last_message_time = asyncio.get_running_loop().time()
        ping_interval = float(
            self.environment_variables.SSE_KEEPALIVE_PING_INTERVAL
        )  # Configurable keepalive ping interval
        # Track consecutive read failures so we can back off and avoid a
        # tight error loop. When the Redis pool is exhausted, every connected
        # client's read fails on each cycle; without backoff this turns into a
        # log-ingestion firehose (one failure per client per cycle, ~once/sec).
        consecutive_errors = 0
        try:
            # Application-level control loop
            while True:
                try:
                    # Process yielded messages one by one
                    message_generator = self.read_messages(
                        topic=stream_topic, last_id=last_id
                    )
                    message_count = 0
                    async for new_id, data in message_generator:
                        # Update the last_id for the next iteration
                        last_id = new_id
                        message_count += 1
                        # Send the data to the client
                        data_str = f"data: {data.model_dump_json()}\n\n"
                        yield data_str
                        last_message_time = asyncio.get_running_loop().time()
                        await asyncio.sleep(0.02)

                    # A read cycle completed without raising — the stream is
                    # healthy again, so reset the backoff/error counter.
                    consecutive_errors = 0

                    # If we didn't get any messages, add a small pause
                    # to prevent tight loops and send keepalive ping if needed
                    if message_count == 0:
                        current_time = asyncio.get_running_loop().time()
                        if current_time - last_message_time >= ping_interval:
                            yield ":ping\n\n"
                            last_message_time = current_time
                        await asyncio.sleep(0.1)
                    else:
                        # Small pause between batches
                        await asyncio.sleep(0.02)
                except asyncio.CancelledError:
                    # Client disconnected, exit the loop
                    logger.info(
                        f"Client disconnected from SSE stream for task {task_id}"
                    )
                    raise
                except Exception as e:
                    consecutive_errors += 1
                    # Always log the full traceback — nothing is swallowed.
                    # Volume is controlled two ways instead of by dropping
                    # diagnostics: structured JSON logging keeps each traceback
                    # to a single log entry (see utils.logging), and the
                    # exponential backoff below caps how often a sustained
                    # failure can repeat. The failure counter gives context on
                    # how long a stream has been erroring.
                    logger.error(
                        f"Error processing events for task {task_id} "
                        f"(failure #{consecutive_errors}): {e}",
                        exc_info=True,
                    )
                    yield f"data: {TaskStreamErrorEventEntity(type='error', message=str(e)).model_dump_json()}\n\n"
                    # Exponential backoff (capped) so a sustained failure (e.g.
                    # Redis pool exhaustion) doesn't spin a tight per-client
                    # loop hammering Redis and flooding logs.
                    backoff = min(2.0 ** min(consecutive_errors - 1, 5), 30.0)
                    await asyncio.sleep(backoff)

        except asyncio.CancelledError:
            # Just exit the generator on cancellation
            logger.info(f"Client disconnected from SSE stream for task {task_id}")
            pass
        except Exception as e:
            logger.error(
                f"Fatal error in SSE stream for task {task_id}: {e}", exc_info=True
            )
            yield f"data: {TaskStreamErrorEventEntity(type='error', message=str(e)).model_dump_json()}\n\n"
        finally:
            logger.info(f"SSE stream for task {task_id} has ended")
            await self.cleanup_stream(stream_topic)


DStreamsUseCase = Annotated[StreamsUseCase, Depends(StreamsUseCase)]
