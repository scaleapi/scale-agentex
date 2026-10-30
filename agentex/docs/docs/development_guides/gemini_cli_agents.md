# Gemini CLI Agents

A Gemini CLI agent wraps the `gemini` CLI as a local subprocess and streams its output through the [unified harness](streaming_patterns.md#unified-harness-surface-framework-agents). You spawn the CLI in headless mode with `--output-format stream-json`, pass the prompt with `-p`, and hand its newline-delimited JSON stream to a `GeminiCliTurn`. The `UnifiedEmitter` then delivers the canonical `StreamTaskMessage*` events and derives tracing spans automatically, exactly like the Claude Code and Codex harnesses.

Scaffold one with `agentex init` by picking the **Gemini CLI** framework option (available for Sync, Async-base, and Temporal).

## Prerequisites

- The `gemini` CLI installed and on your `PATH` (`npm install -g @google/gemini-cli`).
- A `GEMINI_API_KEY` in the environment (the CLI's other login methods also work in a shell where you have signed in). Optionally `GEMINI_MODEL` to pin a model; the CLI defaults to `auto`.

## How it works

The template spawns the CLI in streaming-JSON mode with the prompt on the command line and stdin closed:

```python
cmd = ["gemini", "-p", prompt, "--output-format", "stream-json"]
if model := os.environ.get("GEMINI_MODEL"):
    cmd.extend(["-m", model])
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.DEVNULL,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

Stdin is closed on purpose: in non-interactive mode the CLI reads stdin to EOF and appends it to the prompt, so an open pipe would make it wait forever.

`GeminiCliTurn(lines)` wraps the iterator of stdout lines (raw JSON strings or pre-parsed dicts). Under the hood it runs the `convert_gemini_cli_to_agentex_events` tap, which maps the CLI's events onto the canonical stream:

| Gemini CLI event | Canonical events |
|---|---|
| `init` | none (session id and model are captured on the turn) |
| `message` (`role: user`) | none (the CLI echoes the prompt) |
| `message` (`role: assistant`, `delta: true`) | `Start(TextContent)` once, then a `Delta(TextDelta)` per chunk; the slot is closed on the next tool event or the `result` |
| `tool_use` | `Start(ToolRequestContent)` + `Done`, keyed by `tool_id` |
| `tool_result` | `Full(ToolResponseContent)` with the output (or the error message and `is_error`) |
| `error` | logged, nothing emitted |
| `result` | closes any open text slot; its `stats` become the turn's `TurnUsage` |

The turn exposes `session_id` and `model` from the `init` event, and `usage()` maps `stats` (`input_tokens`, `output_tokens`, `cached`, `total_tokens`, `duration_ms`, `tool_calls`) onto `TurnUsage`. The CLI does not report cost, so `cost_usd` stays `None`.

## Sync delivery (HTTP yield)

```python
import agentex.lib.adk as adk
from agentex.lib.adk import UnifiedEmitter, GeminiCliTurn

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
        turn = GeminiCliTurn(_spawn_gemini(prompt))  # iterator of CLI stdout lines
        async for event in emitter.yield_turn(turn):
            yield event
```

## Async and Temporal delivery

For Async-base and Temporal agents the body is the same, except you call `auto_send_turn` (which pushes to Redis and returns a `TurnResult`) instead of `yield_turn`. Under Temporal, run the subprocess inside an activity and pass `created_at=workflow.now()`:

```python
result = await emitter.auto_send_turn(turn, created_at=workflow.now())
# result.final_text, result.usage
```

Always tear the subprocess down in a `finally` block so a cancelled or failed turn does not leak a `gemini` process.

## Multi-turn conversations

The Gemini CLI's `--resume` flag takes `latest` or a session index rather than a session id, which is not safe when one worker serves several tasks. The templates therefore run each turn as an independent prompt and keep the reported `session_id` for observability only. If you need conversational memory, carry the relevant history into the prompt yourself.

## Tool approval

The CLI's `--approval-mode` (`default`, `auto_edit`, `yolo`, `plan`) governs what its built-in tools may do without confirmation. The templates do not pass it, so the CLI's default applies; add `--approval-mode yolo` to the spawn only for agents that are meant to run tools unattended, and prefer the CLI's policy engine for anything shared.

## See also

- [Unified Harness Surface](streaming_patterns.md#unified-harness-surface-framework-agents)
- [Observability & Tracing](observability_and_tracing.md)
- [Claude Code Agents](claude_code_agents.md) and [Codex Agents](codex_agents.md), the other CLI harnesses
