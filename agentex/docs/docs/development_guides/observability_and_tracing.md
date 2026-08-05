# Observability & Tracing

Agentex derives tracing spans **automatically** from the canonical message stream. When you deliver a turn through the [unified harness](streaming_patterns.md#unified-harness-surface-framework-agents), the `UnifiedEmitter` watches the same `StreamTaskMessage*` events it sends to the client and opens/closes tool and reasoning spans as a side effect. There is no per-framework tracing handler to wire up (the old `create_<framework>_tracing_handler` helpers have been removed).

## How spans are derived

The emitter runs a small reducer (`SpanDeriver`) over the canonical stream and emits span signals that a `SpanTracer` turns into `adk.tracing` child spans:

- **Tool spans** open when a `ToolRequestContent` index completes and close on the matching `ToolResponseContent`, paired by `tool_call_id`. The span carries the tool arguments as input and the tool result as output, and records `is_error` when the framework reports a failure.
- **Reasoning spans** open on the `Start` of a `ReasoningContent` block and close on that index's `Done`.

Because derivation reads the canonical stream rather than any framework-specific event shape, every harness framework (LangGraph, Pydantic AI, OpenAI Agents, Claude Code, Codex) gets the same spans for free.

## The three tracing modes

`UnifiedEmitter` accepts a `tracer` argument that selects how tracing behaves:

| `tracer=` value | Behavior |
|---|---|
| `None` (default) | Auto-construct a `SpanTracer` when `trace_id` is set. This is the normal path. |
| `False` | Disable span derivation entirely, even when `trace_id` is set. |
| a `SpanTracer` instance | Use the tracer you supply (useful for tests or a custom backend). |

```python
from agentex.lib.core.harness import UnifiedEmitter

# Default: tracing on whenever trace_id is present.
emitter = UnifiedEmitter(task_id=task_id, trace_id=task_id, parent_span_id=None)

# Off: deliver the turn but derive no spans.
emitter = UnifiedEmitter(task_id=task_id, trace_id=task_id, parent_span_id=None, tracer=False)
```

## Nesting derived spans under a turn span

Derived tool and reasoning spans are leaves. To group them under a single parent for each turn, open a span with the `adk.tracing.span` context manager and pass its id as `parent_span_id`:

```python
import agentex.lib.adk as adk
from agentex.lib.adk import UnifiedEmitter, LangGraphTurn

async with adk.tracing.span(
    trace_id=task_id, task_id=task_id, name="message",
    input={"message": user_message},
    data={"__span_type__": "AGENT_WORKFLOW"},
) as turn_span:
    emitter = UnifiedEmitter(
        task_id=task_id, trace_id=task_id,
        parent_span_id=turn_span.id if turn_span else None,
    )
    turn = LangGraphTurn(graph.astream(...))
    async for event in emitter.yield_turn(turn):
        yield event

    if turn_span:
        turn_span.output = {"final_output": turn.usage().model_dump()}
```

Use `adk.tracing.span` for spans the stream cannot infer (the top-level turn, sub-agent calls, custom business logic). Let the emitter handle tool and reasoning spans.

## Turn usage

Both delivery calls expose normalized usage. `auto_send_turn` returns a `TurnResult` with `final_text` and a `usage` object; for `yield_turn`, read `turn.usage()` after the stream is exhausted. `TurnUsage` carries `model`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`, `total_tokens`, `cost_usd`, `duration_ms`, `num_llm_calls`, `num_tool_calls`, and `num_reasoning_blocks`.

## Sending spans to Scale GenAI Platform

Span derivation produces spans; **tracing processors** decide where they go. Register a processor once at module load time (before any request is handled) and every derived span fans out to it:

```python
import os
from agentex.lib.core.tracing.tracing_processor_manager import add_tracing_processor_config
from agentex.lib.types.tracing import SGPTracingProcessorConfig

add_tracing_processor_config(
    SGPTracingProcessorConfig(
        sgp_api_key=os.environ.get("SGP_API_KEY", ""),
        sgp_account_id=os.environ.get("SGP_ACCOUNT_ID", ""),
        sgp_base_url=os.environ.get("SGP_CLIENT_BASE_URL", ""),
    )
)
```

With a processor registered and `trace_id` set on the emitter, tool and reasoning spans appear in the SGP traces UI with no further wiring. To run an agent without emitting spans, either omit the processor or construct the emitter with `tracer=False`.

## Key takeaways

- Tool and reasoning spans are derived from the canonical stream automatically; no per-framework tracing handler.
- `tracer=None` traces when `trace_id` is set, `tracer=False` disables, a `SpanTracer` instance customizes.
- Pass `parent_span_id` from an `adk.tracing.span` to nest derived spans under a turn span.
- Register an `SGPTracingProcessorConfig` once at module load to ship spans to Scale GenAI Platform.
