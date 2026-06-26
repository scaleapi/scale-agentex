# OpenAI Agents SDK + Local Sandbox

The **Local Sandbox** variant is the OpenAI Agents SDK starter wired to run tool calls inside the OpenAI Agents SDK's local (`unix_local`) sandbox. Instead of registering hand-written Python functions as tools, you grant the agent **capabilities** (for example `Shell`) and the SDK runtime turns them into real tools that execute on the host machine where the agent runs. No Docker, Kubernetes, or remote sandbox is involved.

Scaffold one with `agentex init` and pick **Sync ACP + OpenAI Agents SDK + Local Sandbox**. It shares the same harness wiring and tutorial base as the plain [OpenAI Agents SDK](tutorials.md#sync-acp-simple-agents) starter; there is no separate tutorial for it.

## When to use it

- Local development and quick prototyping where an agent needs real shell access (run a command, inspect the filesystem, check a version) without standing up container infrastructure.
- Lightweight agents that introspect the host environment.

Reach for a **remote** sandbox (`DockerSandboxClient`, `K8sSandboxClient`) instead when you need filesystem isolation, resource limits, or a production-grade security boundary. The local sandbox runs commands on the host with no isolation.

## Prerequisites

- A **Unix** host (Linux or macOS). The `unix_local` sandbox raises `ImportError` on Windows; use a remote sandbox there.
- `LITELLM_API_KEY` (or `OPENAI_API_KEY`) in the environment. The template copies `LITELLM_API_KEY` into `OPENAI_API_KEY` for SDK compatibility when only the former is set.

## How it differs from the plain OpenAI Agents starter

| | Plain `sync-openai-agents` | `sync-openai-agents-local-sandbox` |
|---|---|---|
| Agent class | `Agent` | `SandboxAgent` |
| Tools | hand-written `@function_tool` functions | `capabilities=[Shell(), ...]` converted by the runtime |
| Execution | your Python functions | real shell commands on the host via `UnixLocalSandboxClient` |

## How it works

The scaffold splits across three files: `acp.py` (the ACP handler), `agent.py` (the agent and run config), and `tools.py` (the capability list). The agent is built with capabilities, and a `RunConfig` points the runner at the local sandbox backend:

```python
# tools.py
def get_capabilities() -> list:
    return [Shell()]  # add Filesystem(), Memory(), etc. as needed

# agent.py
def create_agent() -> SandboxAgent:
    return SandboxAgent(
        model="gpt-4o-mini",
        instructions="Use your shell tools to answer; do not guess.",
        capabilities=get_capabilities(),
    )

def create_run_config() -> RunConfig:
    return RunConfig(
        sandbox=SandboxRunConfig(
            client=UnixLocalSandboxClient(),
            options=UnixLocalSandboxClientOptions(),
        ),
    )

async def run_agent(user_message: str) -> str:
    result = await Runner.run(
        create_agent(), user_message,
        run_config=create_run_config(), max_turns=10,
    )
    return result.final_output
```

When the model decides to run a command, the OpenAI Agents SDK tool loop calls the sandbox session's `exec` (or `read`/`write` for filesystem capabilities) on the host and feeds the output back to the model. You never call the sandbox client directly.

The ACP handler is the standard sync pattern: it runs the agent and returns a single `TextContent`. Because `Runner.run` returns one final answer rather than a token stream, this variant ships as a Sync ACP agent.

## See also

- [Choose Your Agent Type](../getting_started/choose_your_agent_type.md#pick-a-framework-harness)
- [OpenAI Agents SDK starter tutorials](tutorials.md#sync-acp-simple-agents)
- [Temporal OpenAI Agents Integration](../temporal_development/openai_integration.md) for the durable, tool-rich path
