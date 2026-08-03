import asyncio
import sys
from collections.abc import AsyncIterator, Mapping
from typing import Annotated

from fastapi import Depends
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import ValidationError

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.streams.adapter_redis import DRedisStreamRepository
from src.api.schemas.task_stream_events import TaskStreamEvent
from src.config.dependencies import DEnvironmentVariables
from src.domain.entities.task_stream_events import (
    TaskStreamConnectedEventEntity,
    TaskStreamErrorEventEntity,
    TaskStreamEventEntity,
    TaskStreamTaskUpdatedEventEntity,
    convert_task_stream_event_to_entity,
)
from src.domain.entities.tasks import TERMINAL_TASK_STATUSES
from src.domain.services.task_service import DAgentTaskService
from src.utils.logging import make_logger
from src.utils.stream_topics import get_task_event_stream_topic

logger = make_logger(__name__)

# ProxyTracer: resolves to the process TracerProvider lazily at span-creation
# time, so this is safe to bind at import even when tracing is configured later
# (and a no-op when no provider is installed).
_TRACER = trace.get_tracer("agentex.task_stream")


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
        carrier: Mapping[str, str] | None = None,
    ) -> AsyncIterator[str]:
        """
        Async generator for streaming task message updates as SSE data strings.
        Sends keepalive pings to maintain long-lived connections.

        Each call runs under its own OpenTelemetry span whose parent is taken
        *only* from the inbound W3C ``traceparent`` (``carrier``) or, absent one,
        a fresh root — never the ambient context. The SSE body is pumped by the
        ASGI server long after the request handler returned, so the ambient
        context can still carry a previous request's span; inheriting it made a
        stream's logs and child spans resolve to an unrelated, long-lived trace
        (cross-request context bleed). Anchoring to an isolated context and
        attaching it for the stream's lifetime keeps every stream self-contained.
        """
        # Parent the stream span on the ingress traceparent alone. The empty
        # ``Context()`` base is the isolation: ``extract`` otherwise falls back to
        # the current (possibly stale) context, which is exactly the bleed. With
        # no inbound traceparent this yields a fresh root; with one, a child.
        parent_context = extract(dict(carrier) if carrier else {}, context=Context())
        span = _TRACER.start_span(
            "stream task events",
            context=parent_context,
            kind=SpanKind.SERVER,
        )
        # Attach the span as current for the stream's lifetime so log lines
        # correlate to this trace (fixing the "otelTraceID resolves to an
        # unrelated trace" symptom) and any downstream spans nest under it.
        context_token = otel_context.attach(
            trace.set_span_in_context(span, parent_context)
        )

        # Lifecycle outcome, finalized on the span in ``finally``. Defaults assume
        # a clean server-side end; each termination path narrows the reason.
        stream_outcome = "completed"
        disconnect_reason = "completed"
        first_event_recorded = False

        def _record_first_event() -> None:
            # Time-to-first-event marker: the first real task event delivered
            # (the synthetic "connected" frame and keepalive pings don't count).
            nonlocal first_event_recorded
            if not first_event_recorded:
                first_event_recorded = True
                span.add_event("first-event")

        span.add_event("open")
        try:
            if not task_id:
                if not task_name:
                    raise ValueError("Either task_id or task_name must be provided")

                task = await self.task_service.get_task(name=task_name)
                task_id = task.id
            span.set_attribute("task.id", task_id)

            stream_topic = get_task_event_stream_topic(task_id=task_id)
            # Cursor before status read: catches a racing terminal event.
            last_id = await self.stream_repository.get_stream_tail_id(stream_topic)
            task = await self.task_service.get_task(id=task_id)
            # Send initial connection data
            yield f"data: {TaskStreamConnectedEventEntity(type='connected', taskId=task_id).model_dump_json()}\n\n"
            # Already terminal: replay buffered events and end (late connect).
            if task.status in TERMINAL_TASK_STATUSES:
                async for _id, data in self.read_messages(
                    topic=stream_topic, last_id="0"
                ):
                    _record_first_event()
                    yield f"data: {data.model_dump_json()}\n\n"
                    await asyncio.sleep(0.02)
                disconnect_reason = "already_terminal"
                logger.info(
                    f"Ending SSE stream for task {task_id}: already terminal at connect"
                )
                return

            last_message_time = asyncio.get_running_loop().time()
            ping_interval = float(
                self.environment_variables.SSE_KEEPALIVE_PING_INTERVAL
            )  # Configurable keepalive ping interval
            # Track consecutive read failures so we can back off and avoid a
            # tight error loop. When the Redis pool is exhausted, every connected
            # client's read fails on each cycle; without backoff this turns into a
            # log-ingestion firehose (one failure per client per cycle, ~once/sec).
            consecutive_errors = 0
            last_status_check = last_message_time
            # Application-level control loop
            while True:
                try:
                    # Authoritative status recheck on an interval. Runs at the
                    # TOP of every iteration — even after a read failure/backoff
                    # — so a terminal task ends even if its event publish was
                    # lost or Redis reads keep erroring.
                    current_time = asyncio.get_running_loop().time()
                    if current_time - last_status_check >= ping_interval:
                        last_status_check = current_time
                        try:
                            task = await self.task_service.get_task(id=task_id)
                        except ItemDoesNotExist:
                            # Row permanently gone (e.g. retention) — end.
                            stream_outcome = "task_gone"
                            disconnect_reason = "task_deleted"
                            logger.info(
                                f"Ending SSE stream for task {task_id}: "
                                "task no longer exists"
                            )
                            return
                        if task.status in TERMINAL_TASK_STATUSES:
                            disconnect_reason = "terminal_status"
                            logger.info(
                                f"Ending SSE stream for task {task_id}: "
                                "terminal on status recheck"
                            )
                            return

                    # Process yielded messages one by one
                    message_generator = self.read_messages(
                        topic=stream_topic, last_id=last_id
                    )
                    message_count = 0
                    async for new_id, data in message_generator:
                        # Update the last_id for the next iteration
                        last_id = new_id
                        message_count += 1
                        _record_first_event()
                        # Send the data to the client
                        data_str = f"data: {data.model_dump_json()}\n\n"
                        yield data_str
                        last_message_time = asyncio.get_running_loop().time()
                        # Terminal event is the last one — end here.
                        if (
                            isinstance(data, TaskStreamTaskUpdatedEventEntity)
                            and data.task is not None
                            and data.task.status in TERMINAL_TASK_STATUSES
                        ):
                            disconnect_reason = "terminal_event"
                            logger.info(
                                f"Ending SSE stream for task {task_id}: received "
                                "a terminal task_updated event"
                            )
                            return
                        await asyncio.sleep(0.02)

                    # A read cycle completed without raising — the stream is
                    # healthy again, so reset the backoff/error counter.
                    consecutive_errors = 0

                    # Idle: send keepalive ping so proxies don't reap us. Use a
                    # fresh timestamp — the read above blocks up to timeout_ms,
                    # so the loop-top current_time would be stale for ping timing.
                    if message_count == 0:
                        now = asyncio.get_running_loop().time()
                        if now - last_message_time >= ping_interval:
                            yield ":ping\n\n"
                            last_message_time = now
                        await asyncio.sleep(0.1)
                    else:
                        # Small pause between batches
                        await asyncio.sleep(0.02)
                except asyncio.CancelledError:
                    # Client disconnected, exit the loop
                    stream_outcome = "client_disconnect"
                    disconnect_reason = "client_disconnect"
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
            stream_outcome = "client_disconnect"
            disconnect_reason = "client_disconnect"
            logger.info(f"Client disconnected from SSE stream for task {task_id}")
            pass
        except Exception as e:
            stream_outcome = "error"
            disconnect_reason = type(e).__name__
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error(
                f"Fatal error in SSE stream for task {task_id}: {e}", exc_info=True
            )
            yield f"data: {TaskStreamErrorEventEntity(type='error', message=str(e)).model_dump_json()}\n\n"
        finally:
            # Safety net for an exception that bypassed the except clauses above
            # and is still in flight — chiefly Starlette aborting the SSE body
            # with GeneratorExit on client disconnect, which is a BaseException
            # that `except Exception` doesn't see. Only reclassify when no
            # handler already set an outcome.
            in_flight = sys.exc_info()[1]
            if in_flight is not None and stream_outcome == "completed":
                if isinstance(in_flight, GeneratorExit | asyncio.CancelledError):
                    stream_outcome = "client_disconnect"
                    disconnect_reason = "client_disconnect"
                else:
                    stream_outcome = "error"
                    disconnect_reason = type(in_flight).__name__
                    span.record_exception(in_flight)
                    span.set_status(Status(StatusCode.ERROR, str(in_flight)))
            span.set_attribute("stream.outcome", stream_outcome)
            span.set_attribute("disconnect.reason", disconnect_reason)
            span.add_event(
                "close",
                {
                    "stream.outcome": stream_outcome,
                    "disconnect.reason": disconnect_reason,
                },
            )
            span.end()
            otel_context.detach(context_token)
            # Don't delete the shared topic; the TTL reclaims it.
            logger.info(f"SSE stream for task {task_id} has ended")


DStreamsUseCase = Annotated[StreamsUseCase, Depends(StreamsUseCase)]
