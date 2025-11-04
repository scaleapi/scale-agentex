# Tutorials

**All hands-on tutorials are maintained in the Agentex Python repository.**

**[→ Browse Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials)**

## Available Tutorials

### Sync ACP (Simple Agents)

Perfect for learning basic agent patterns with simple request-response interactions.

- **[Hello ACP](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/00_sync/000_hello_acp)** - Your first agent in 5 minutes
- **[Multiturn](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/00_sync/010_multiturn)** - Add conversation history and memory
- **[Streaming](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/00_sync/020_streaming)** - Stream real-time responses to clients

### Async ACP - Base (Learning & Development)

Learn stateful workflows with full lifecycle control. Great for development and understanding advanced patterns.

- **[Hello Async ACP](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/000_hello_acp)** - Three-handler pattern fundamentals
- **[Multiturn](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/010_multiturn)** - Build stateful conversations
- **[Streaming](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/020_streaming)** - Stream responses in complex workflows
- **[Tracing](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/030_tracing)** - Add observability and debugging
- **[Other SDKs](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/040_other_sdks)** - Integrate OpenAI Agents SDK and MCP
- **[Batch Events](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/080_batch_events)** - Handle multiple events efficiently
- **[Multi-Agent Assembly Line](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/00_base/090_multi_agent_non_temporal)** - Coordinate multiple agents without Temporal

### Async ACP - Temporal (Production)

Enterprise-ready patterns with durable execution. For production deployments requiring reliability and fault tolerance.

- **[Hello Temporal](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/000_hello_acp)** - Your first Temporal workflow
- **[Agent Chat](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/010_agent_chat)** - LLM chat with tools integration
- **[State Machine](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/020_state_machine)** - Complex workflow orchestration
- **[Custom Activities](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/030_custom_activities)** - Build custom activities for external operations
- **[Agent Chat with Guardrails](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/050_agent_chat_guardrails)** - Add safety and validation to agent conversations
- **[OpenAI Agents SDK Integration](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/)** - Build production-ready agents with OpenAI SDK + Temporal
  - [OpenAI Agents SDK: Hello World](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/060_open_ai_agents_sdk_hello_world) - Automatic durability for LLM calls
  - [OpenAI Agents SDK: Tools](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/070_open_ai_agents_sdk_tools) - Single and multi-activity tool patterns
  - [OpenAI Agents SDK: Human-in-the-Loop](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/080_open_ai_agents_sdk_human_in_the_loop) - Wait for human approval with child workflows

## Why Tutorials are on GitHub

✅ **Runnable code** - Clone the repository and run examples immediately
✅ **Always up-to-date** - Code is tested with each SDK release
✅ **Complete projects** - Full file structure and dependencies, not just snippets
✅ **Community contributions** - Submit PRs to improve examples
✅ **Version alignment** - Tutorial code matches the SDK version you're using

## Learning Path

**1. Start with Sync ACP**
Understand the basics of agent development with simple request-response patterns.

**2. Progress to Async Base**
Learn stateful workflows, event handling, and complex agent patterns.

**3. Move to Temporal**
Master production-ready patterns with durable execution and enterprise reliability.

## Running Tutorials Locally

```bash
# Clone the repository
git clone https://github.com/scaleapi/scale-agentex-python.git
cd scale-agentex-python/examples/tutorials

# Navigate to a tutorial
cd 00_sync/000_hello_acp

# Follow the README in each tutorial directory
cat README.md
```

## Prerequisites

Before starting any tutorial:

1. **Agentex SDK installed**: `pip install agentex-sdk`
2. **Development environment set up**: Follow the [Quick Start Guide](https://github.com/scaleapi/scale-agentex#quick-start)
3. **Basic Python knowledge**: Familiarity with async/await patterns

