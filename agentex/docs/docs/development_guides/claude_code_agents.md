# Claude Code Agents

A Claude Code agent wraps the `claude` CLI as a local subprocess and streams its output through the [unified harness](streaming_patterns.md#unified-harness-surface-framework-agents). You spawn the CLI, feed the prompt on stdin, and hand its newline-delimited JSON stream to a `ClaudeCodeTurn`. The `UnifiedEmitter` then delivers the canonical `StreamTaskMessage*` events and derives tracing spans automatically, exactly like any other harness framework.

Scaffold one with `agentex init` by picking the **Claude Code** framework option (available for Sync, Async-base, and Temporal).

## Prerequisites

- The `claude` CLI installed and on your `PATH`.
- An `ANTHROPIC_API_KEY` (or equivalent credential) in the environment. The CLI authenticates with this key directly; it is not routed through LiteLLM.

## How it works

The template spawns the CLI in streaming-JSON mode and writes the prompt to stdin:

```python
proc = await asyncio.create_subprocess_exec(
    "claude", "-p", "--output-format", "stream-json", "--verbose",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
proc.stdin.write(prompt.encode())
await proc.stdin.drain()
proc.stdin.close()
```

`ClaudeCodeTurn(lines)` wraps the iterator of stdout lines (raw JSON strings or pre-parsed dicts). Under the hood it runs the `convert_claude_code_to_agentex_events` tap, which converts the CLI's events into the canonical stream (text, reasoning, tool requests, and tool responses). The turn exposes a `session_id` property so you can resume a conversation on the next turn.

## Sync delivery (HTTP yield)

```python
import agentex.lib.adk as adk
from agentex.lib.adk import UnifiedEmitter, ClaudeCodeTurn

@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    task_id = params.task.id
    async with adk.tracing.span(
        trace_id=task_id, task_id=task_id, name="message",
        input={"message": prompt},
        data={"__span_type__": "AGENT_WORKFLOW"},
    ) as turn_span:
        emitter = UnifiedEmitter(
            task_id=task_id, trace_id=task_id,
            parent_span_id=turn_span.id if turn_span else None,
        )
        turn = ClaudeCodeTurn(_spawn_claude(prompt))  # iterator of CLI stdout lines
        async for event in emitter.yield_turn(turn):
            yield event
```

## Async and Temporal delivery

For Async-base and Temporal agents the body is the same, except you call `auto_send_turn` (which pushes to Redis and returns a `TurnResult`) instead of `yield_turn`. Under Temporal, run the subprocess inside an activity and pass `created_at=workflow.now()`:

```python
result = await emitter.auto_send_turn(turn, created_at=workflow.now())
# result.final_text, result.usage
```

Always tear the subprocess down in a `finally` block so a cancelled or failed turn does not leak a `claude` process.

## See also

- [Unified Harness Surface](streaming_patterns.md#unified-harness-surface-framework-agents)
- [Observability & Tracing](observability_and_tracing.md)
- [Claude Code starter tutorials](tutorials.md) (Sync, Async-base, Temporal)
- [Codex Agents](codex_agents.md) for the OpenAI coding CLI equivalent
