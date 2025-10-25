# Introduction to Agentex

AI agent capabilities can be understood in five levels, from simple chatbots to fully autonomous, self-driving agentic systems:

![Levels of AI Agents](images/levels_of_ai.png)

Today, most AI applications are limited to Level 3 (L3) and below, relying on synchronous request/response patterns. This restricts their ability to handle complex, long-running, or autonomous workflows.

**Agentex** is designed to be future-proof, enabling you to build, deploy, and scale agents at any level (L1–L5). As your needs grow, you can seamlessly progress from basic to advanced agentic AI—without changing your core architecture.

!!! note "Agentex is for all levels of AI agents"
    While Agentex is built to support advanced L4+ agents, it natively supports L1–L3 agents and simple request/response agents as well. You can start with basic conversational or task-based AI and seamlessly progress to fully autonomous, distributed, and asynchronous agents—all on the same platform. Agentex is future-proofed for a world where AI will be distributed across all levels.

## 🚀 Get Started

**Ready to build your first agent?**

**[→ Quick Start Guide on GitHub](https://github.com/scaleapi/scale-agentex#quick-start)** (5 minutes)

The README will guide you through:

- Installing prerequisites (Docker, Python 3.12+)
- Setting up your local development environment
- Creating and running your first agent with `agentex init`
- Accessing the web UI to interact with your agent

**Then return here to dive deeper:**

## Learning Path 🎓

### 1. Choose Your Approach

Read [Developing Agentex Agents](developing_agentex_agents.md) to understand the different approaches (Sync, Agentic, Temporal) and decide which fits your use case.

### 2. Learn by Example

**[Browse Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials)** - Complete, runnable examples:

- **Sync ACP** - Simple request/response agents
- **Agentic ACP** - Stateful workflows and complex agents
- **Temporal** - Production-ready enterprise patterns

### 3. Understand the Architecture

Learn how Agentex works at a system level:

- [Architecture Overview](concepts/architecture.md) - System design and message flow
- [Agent-to-Client Protocol (ACP)](acp/overview.md) - Communication protocol details

!!! warning "Important"
    Pay special attention to the [Critical Concepts](concepts/callouts/overview.md) - they contain essential information about race conditions, message handling, and other implementation details.

### 4. Configure & Deploy

- [Manifest Setup](manifest_setup.md) - Agent configuration and deployment specifications
- [Deployment Guide](deployment/overview.md) - Deploy using CI/CD pipelines

### 5. API Reference

Keep the [API Reference](api/overview.md) handy for detailed Python SDK documentation when building your agents.

---

Scale's Agentic Infrastructure is deployed as part of the [Scale GenAI Platform](https://scale.com/genai-platform). To get your own private enterprise deployment, book a demo with Scale's Enterprise sales team.
