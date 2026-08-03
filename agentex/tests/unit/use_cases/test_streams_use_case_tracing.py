"""Tracing tests for the SSE task-event stream.

These lock in the AGX1-617 fixes:

1. Each stream runs under its own span, isolated from the ambient OTel context —
   a stream must never nest under a leftover span from an unrelated request
   (the cross-request "context bleed" that made a /stream log's trace resolve to
   a multi-hour, thousands-of-spans trace).
2. When the caller supplies a W3C ``traceparent`` (ingress edge), the stream
   span continues that trace as a child rather than starting a new root.
3. The span carries the ``open`` / ``first-event`` / ``close`` lifecycle events
   and the ``task.id`` / ``stream.outcome`` / ``disconnect.reason`` attributes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from src.domain.entities.tasks import TaskStatus
from src.domain.use_cases import streams_use_case as streams_module
from src.domain.use_cases.streams_use_case import StreamsUseCase

# A well-formed W3C traceparent (version-traceid-spanid-flags), sampled.
_INBOUND_TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736
_INBOUND_PARENT_SPAN_ID = 0x00F067AA0BA902B7
_INBOUND_TRACEPARENT = f"00-{_INBOUND_TRACE_ID:032x}-{_INBOUND_PARENT_SPAN_ID:016x}-01"

_SPAN_NAME = "stream task events"


class _FakeStreamRepository:
    """Minimal stream repo: a fixed tail id and a fixed buffered replay."""

    def __init__(self, buffered: list[tuple[str, dict]] | None = None):
        self._buffered = buffered or []

    async def get_stream_tail_id(self, topic: str) -> str:
        return "0-0"

    async def read_messages(
        self, topic: str, last_id: str, timeout_ms: int = 2000, count: int = 10
    ) -> AsyncIterator[tuple[str, dict]]:
        for message_id, obj in self._buffered:
            yield message_id, obj


class _FakeTaskService:
    """Returns a single task for both id and name lookups."""

    def __init__(self, task: SimpleNamespace):
        self._task = task

    async def get_task(self, id=None, name=None) -> SimpleNamespace:
        return self._task


def _make_use_case(
    *,
    status: TaskStatus,
    buffered: list[tuple[str, dict]] | None = None,
    task_id: str = "task-123",
) -> StreamsUseCase:
    task = SimpleNamespace(id=task_id, status=status)
    return StreamsUseCase(
        stream_repository=_FakeStreamRepository(buffered),
        task_service=_FakeTaskService(task),
        environment_variables=SimpleNamespace(
            SSE_KEEPALIVE_PING_INTERVAL=15,
            SSE_STREAM_STALL_THRESHOLD_SECONDS=30,
        ),
    )


@pytest.fixture
def span_exporter(monkeypatch) -> InMemorySpanExporter:
    """Route the module's tracer to an in-memory exporter for assertions."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(streams_module, "_TRACER", provider.get_tracer("test"))
    # Stash the provider so tests can mint a "stale" ambient span from it.
    exporter._test_provider = provider  # type: ignore[attr-defined]
    return exporter


def _only_stream_span(exporter: InMemorySpanExporter):
    spans = [s for s in exporter.get_finished_spans() if s.name == _SPAN_NAME]
    assert len(spans) == 1, f"expected exactly one stream span, got {len(spans)}"
    return spans[0]


async def _drain(gen) -> None:
    async for _ in gen:
        pass


@pytest.mark.unit
@pytest.mark.asyncio
class TestStreamTracing:
    async def test_stream_span_is_isolated_root_when_no_traceparent(
        self, span_exporter
    ):
        # A stale span is active in the ambient context, mimicking a previous
        # request whose context leaked. The stream must NOT nest under it.
        provider = span_exporter._test_provider  # type: ignore[attr-defined]
        stale = provider.get_tracer("stale").start_span("POST /unrelated")
        token = otel_context.attach(trace.set_span_in_context(stale))
        try:
            uc = _make_use_case(status=TaskStatus.COMPLETED)
            await _drain(uc.stream_task_events(task_id="task-123"))
        finally:
            otel_context.detach(token)
            stale.end()

        span = _only_stream_span(span_exporter)
        # No parent → a brand-new root, on a different trace than the stale span.
        assert span.parent is None
        assert span.context.trace_id != stale.get_span_context().trace_id

    async def test_stream_span_continues_inbound_traceparent(self, span_exporter):
        uc = _make_use_case(status=TaskStatus.COMPLETED)
        await _drain(
            uc.stream_task_events(
                task_id="task-123",
                carrier={"traceparent": _INBOUND_TRACEPARENT},
            )
        )

        span = _only_stream_span(span_exporter)
        # Same trace as the caller, parented on the caller's span id.
        assert span.context.trace_id == _INBOUND_TRACE_ID
        assert span.parent is not None
        assert span.parent.span_id == _INBOUND_PARENT_SPAN_ID

    async def test_inbound_traceparent_wins_over_ambient_context(self, span_exporter):
        # Even with a (stale) ambient span active, the ingress traceparent — not
        # the ambient context — must decide the parent.
        provider = span_exporter._test_provider  # type: ignore[attr-defined]
        stale = provider.get_tracer("stale").start_span("POST /unrelated")
        token = otel_context.attach(trace.set_span_in_context(stale))
        try:
            uc = _make_use_case(status=TaskStatus.COMPLETED)
            await _drain(
                uc.stream_task_events(
                    task_id="task-123",
                    carrier={"traceparent": _INBOUND_TRACEPARENT},
                )
            )
        finally:
            otel_context.detach(token)
            stale.end()

        span = _only_stream_span(span_exporter)
        assert span.context.trace_id == _INBOUND_TRACE_ID
        assert span.context.trace_id != stale.get_span_context().trace_id

    async def test_lifecycle_events_and_attributes_on_clean_end(self, span_exporter):
        # Already-terminal task replays one buffered event, then ends cleanly.
        buffered = [("1-0", {"type": "error", "message": "buffered"})]
        uc = _make_use_case(status=TaskStatus.COMPLETED, buffered=buffered)
        await _drain(uc.stream_task_events(task_id="task-123"))

        span = _only_stream_span(span_exporter)
        event_names = [e.name for e in span.events]
        assert event_names == ["open", "first-event", "close"]
        assert span.attributes["task.id"] == "task-123"
        assert span.attributes["stream.outcome"] == "completed"
        assert span.attributes["disconnect.reason"] == "already_terminal"

    async def test_first_event_absent_when_no_events_delivered(self, span_exporter):
        # Terminal-at-connect with nothing buffered: open/close only.
        uc = _make_use_case(status=TaskStatus.COMPLETED)
        await _drain(uc.stream_task_events(task_id="task-123"))

        span = _only_stream_span(span_exporter)
        assert [e.name for e in span.events] == ["open", "close"]

    async def test_client_disconnect_is_recorded_on_aclose(self, span_exporter):
        # Non-terminal task: the generator suspends at the "connected" yield.
        # Closing it (as Starlette does on client disconnect) raises GeneratorExit
        # into the generator, which must be classified as a client disconnect.
        uc = _make_use_case(status=TaskStatus.RUNNING)
        gen = uc.stream_task_events(task_id="task-123")
        first = await gen.__anext__()
        assert "connected" in first
        await gen.aclose()

        span = _only_stream_span(span_exporter)
        assert span.attributes["stream.outcome"] == "client_disconnect"
        assert span.attributes["disconnect.reason"] == "client_disconnect"

    async def test_span_ends_exactly_once_and_detaches_context(self, span_exporter):
        # After the stream ends, the ambient context must be clean (the attached
        # stream context was detached), so a later span is a fresh root.
        uc = _make_use_case(status=TaskStatus.COMPLETED)
        await _drain(uc.stream_task_events(task_id="task-123"))

        # No stream span should be lingering as the current span.
        current = trace.get_current_span()
        assert current.get_span_context().trace_id == 0  # INVALID → nothing attached

    async def test_setup_failure_emits_error_frame_and_marks_span(self, span_exporter):
        # A failure during setup (here, the initial task lookup) must produce the
        # established SSE error frame rather than escaping the generator — which
        # would surface to the client as a broken stream — and the span must be
        # marked errored.
        class _BoomTaskService:
            async def get_task(self, id=None, name=None):
                raise RuntimeError("boom")

        uc = StreamsUseCase(
            stream_repository=_FakeStreamRepository(),
            task_service=_BoomTaskService(),
            environment_variables=SimpleNamespace(
                SSE_KEEPALIVE_PING_INTERVAL=15,
                SSE_STREAM_STALL_THRESHOLD_SECONDS=30,
            ),
        )
        frames = [chunk async for chunk in uc.stream_task_events(task_id="task-123")]

        # The generator completed normally, yielding a parseable SSE error frame.
        assert frames, "expected an SSE error frame, got nothing"
        assert frames[-1].startswith("data: ")
        assert '"type":"error"' in frames[-1]
        assert "boom" in frames[-1]

        span = _only_stream_span(span_exporter)
        assert span.attributes["stream.outcome"] == "error"
        assert span.attributes["disconnect.reason"] == "RuntimeError"
