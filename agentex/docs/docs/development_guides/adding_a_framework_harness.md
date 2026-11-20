# Adding a Framework Harness

Agentex already ships harnesses for the OpenAI Agents SDK, Pydantic AI, LangGraph, Claude Code, and Codex. Each one is a thin **tap** that translates the framework's native event stream into the canonical `StreamTaskMessage*` stream, plus a `HarnessTurn` wrapper. Everything else (streaming delivery, span derivation, tracing, usage) is shared, so adding a framework is mostly plumbing. This page lists exactly what to add, mirroring the Claude Code harness, which is the simplest complete example.

All paths below are in the [scale-agentex-python](https://github.com/scaleapi/scale-agentex-python) repository unless noted.

## 1. The tap and the turn (required)

| File | What it contains |
|---|---|
| `src/agentex/lib/adk/_modules/_<fw>_sync.py` | `convert_<fw>_to_agentex_events(...)`: an async generator that consumes the framework's native stream and yields `StreamTaskMessageStart` / `Delta` / `Full` / `Done` events. Use a stable `index` per content slot and `tool_call_id` on tool request/response content so spans pair up. |
| `src/agentex/lib/adk/_modules/_<fw>_turn.py` | `<Fw>Turn`: implements the `HarnessTurn` protocol (`events` property returning the tap's stream, `usage()` returning a `TurnUsage` once the stream is exhausted). Extract tokens, cost, duration, and call counts from the framework's final result. |
| `src/agentex/lib/adk/__init__.py` | Export both names so users can `from agentex.lib.adk import <Fw>Turn, convert_<fw>_to_agentex_events`. |

Reference implementations: `_claude_code_sync.py` / `_claude_code_turn.py` (subprocess stream of newline-delimited JSON) and `_codex_sync.py` / `_codex_turn.py`. The protocol and shared machinery are documented in `adk/docs/harness.md` and in [Streaming Patterns](streaming_patterns.md#unified-harness-surface-framework-agents).

There is **no** per-framework streamer or tracing handler to write: `UnifiedEmitter.yield_turn` (sync ACP) and `auto_send_turn` (async / Temporal) deliver the stream and derive tool and reasoning spans from it.

## 2. Tests (required)

| File | What it covers |
|---|---|
| `tests/lib/adk/test_<fw>_sync.py` | The tap: feed recorded native events, assert the exact canonical events (types, indices, tool ids, text). |
| `tests/lib/adk/test_<fw>_turn.py` | The turn: `usage()` fields, `HarnessTurn` protocol compliance. |
| `tests/lib/core/harness/test_harness_<fw>_sync.py` and `_async.py` (and `_temporal.py` if you ship a Temporal template) | End to end through `UnifiedEmitter`: events reach the caller / task stream and spans are derived. |

Tests run offline against recorded fixtures; see the Claude Code tests for the fixture shape.

## 3. Templates for `agentex init` (recommended)

Add one directory per agent type under `src/agentex/lib/cli/templates/`:

- `sync-<fw>/` (Sync ACP), `default-<fw>/` (Async base), `temporal-<fw>/` (Temporal; the framework call runs inside an activity, and `auto_send_turn(..., created_at=workflow.now())` is used).

Copy the matching `*-claude-code` directory and adjust `project/acp.py.j2` (or `workflow.py.j2` + `activities.py.j2`), `README.md.j2`, `manifest.yaml.j2` (credentials), and `pyproject.toml.j2` (dependencies). Then register the new `TemplateType` values and their file lists in `src/agentex/lib/cli/commands/init.py` and add them to the `agentex init` menus in the same file.

## 4. Tutorials and docs (recommended)

- Tutorials: `examples/tutorials/00_sync/0x0_<fw>`, `examples/tutorials/10_async/00_base/1x0_<fw>`, and `examples/tutorials/10_async/10_temporal/1x0_<fw>`, each with `tests/test_agent.py` (offline tests always run; live tests gated behind an environment variable).
- Docs (this repository, `agentex/docs/docs/`): a `development_guides/<fw>_agents.md` page like [Claude Code Agents](claude_code_agents.md), a row in the framework table in [Choose Your Agent Type](../getting_started/choose_your_agent_type.md#pick-a-framework-harness), and a nav entry under **Framework Agents** in `agentex/docs/mkdocs.yml`.

## Checklist

- [ ] Tap yields only `StreamTaskMessage*` events with stable indices and `tool_call_id`s
- [ ] `<Fw>Turn.usage()` is populated after the stream is exhausted
- [ ] Both exported from `agentex.lib.adk`
- [ ] Tap, turn, and harness tests pass offline
- [ ] Templates registered in `init.py` and scaffold cleanly with `agentex init`
- [ ] Tutorial(s) and a docs page, nav entry added
