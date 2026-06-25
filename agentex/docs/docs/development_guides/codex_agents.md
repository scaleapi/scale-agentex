# Codex Agents

A Codex agent wraps the `codex` CLI as a local subprocess and streams its output through the [unified harness](streaming_patterns.md#unified-harness-surface-framework-agents). It is the OpenAI coding-CLI counterpart to a [Claude Code agent](claude_code_agents.md): you spawn the CLI, feed the prompt on stdin, and hand its newline-delimited JSON events to a `CodexTurn`. The `UnifiedEmitter` delivers the canonical `StreamTaskMessage*` events and derives tracing spans automatically.

Scaffold one with `agentex init` by picking the **Codex** framework option (available for Sync, Async-base, and Temporal).

## Prerequisites

- The `codex` CLI installed and on your `PATH` (`npm install -g @openai/codex`).
- An `OPENAI_API_KEY` in the environment. The CLI authenticates with this key directly.
- Optionally set `CODEX_MODEL` to choose the model (defaults to `o4-mini`).

## How it works

The template spawns the CLI in JSON-event mode and writes the prompt to stdin:

```python
cmd = [
    "codex", "exec", "--json",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
    "--model", model,
    "-",  # read the prompt from stdin
]
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.DEVNULL,
    env={**os.environ},
)
```

`--dangerously-bypass-approvals-and-sandbox` skips the CLI's interactive approval prompts, which is required when running headless in a server. `CodexTurn(events, model=..., duration_ms=..., cost_usd=...)` wraps the iterator of stdout events. The tap `convert_codex_to_agentex_events` converts the codex events into the canonical stream and exposes a `session_id` (the codex `thread_id`) for resuming a conversation with `codex exec resume <thread_id>`.

Codex does not report wall-clock time in its event stream, so set `turn.duration_ms` yourself after the stream finishes if you want it in usage.

## Sync delivery (HTTP yield)

```python
import os
import time
import agentex.lib.adk as adk
from agentex.lib.adk import UnifiedEmitter, CodexTurn

MODEL = os.environ.get("CODEX_MODEL", "o4-mini")

@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    task_id = params.task.id
    start_ms = int(time.monotonic() * 1000)
    async with adk.tracing.span(
        trace_id=task_id, task_id=task_id, name="message",
        input={"message": user_message},
        data={"__span_type__": "AGENT_WORKFLOW"},
    ) as turn_span:
        process = await _spawn_codex(MODEL)
        process.stdin.write(user_message.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        turn = CodexTurn(events=_process_stdout(process), model=MODEL)
        emitter = UnifiedEmitter(
            task_id=task_id, trace_id=task_id,
            parent_span_id=turn_span.id if turn_span else None,
        )
        try:
            async for event in emitter.yield_turn(turn):
                yield event
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
        turn.duration_ms = int(time.monotonic() * 1000) - start_ms
```

## Async and Temporal delivery

For Async-base and Temporal agents the body is the same, except you call `auto_send_turn` instead of `yield_turn`. Under Temporal, run the subprocess inside an activity and pass `created_at=workflow.now()`; pass the stored `thread_id` to resume the codex session across turns:

```python
result = await emitter.auto_send_turn(turn, created_at=workflow.now())
# result.final_text, result.usage; persist turn.session_id to resume next turn
```

Always tear the subprocess down in a `finally` block so a cancelled or failed turn does not leak a `codex` process.

## See also

- [Unified Harness Surface](streaming_patterns.md#unified-harness-surface-framework-agents)
- [Observability & Tracing](observability_and_tracing.md)
- [Codex starter tutorials](tutorials.md) (Sync, Async-base, Temporal)
- [Claude Code Agents](claude_code_agents.md) for the Anthropic coding CLI equivalent
