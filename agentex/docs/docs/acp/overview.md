# Agent-to-Client Protocol (ACP)

The Agent-to-Client Protocol (ACP) is the foundation of how agents communicate with clients in Agentex. Understanding ACP is essential for building effective agents and choosing the right architecture for your use case.

## What is ACP?

**ACP (Agent-to-Client Protocol)** defines the communication contract between agents and clients. It specifies:

- **Message formats** for different types of interactions
- **Handler methods** that agents must implement
- **Lifecycle management** for conversations and workflows
- **Data flow patterns** between clients and agents

Think of ACP as the "language" that agents and clients use to understand each other.

---

## ACP Types Overview

Agentex supports two distinct ACP types, each designed for different use cases:

| Feature | Sync ACP | Async ACP |
|---------|----------|-------------|
| **Best for** | Chat bots, simple Q&A | Complex workflows, stateful apps |
| **Handlers** | 1 method (`on_message_send`) | 3 methods (`on_task_create`, `on_task_event_send`, `on_task_cancel`) |
| **State Management** | Automatic/optional | Manual, full control |
| **Message Management** | Automatic | Manual |
| **Complexity** | Minimal | Higher |
| **Task Lifecycle** | Automatic | Manual |

### Quick Decision Guide

**Use Sync ACP when:**

- ✅ Simple interactions - Direct question and answer patterns
- ✅ Stateless processing - Each message is independent
- ✅ Quick responses - Fast, lightweight operations
- ✅ Chat-like interfaces - Traditional conversational AI

**Use Async ACP when:**

- ✅ Complex workflows - Multi-step processes with state
- ✅ Persistent memory - Need to remember context across interactions
- ✅ Event-driven logic - Responses depend on workflow stage
- ✅ Resource management - Need initialization and cleanup
- ✅ Advanced features - Streaming, tracing, coordination

---

## Learn More

### Sync ACP

Perfect for simple chat bots and Q&A agents. Get started with the easiest approach.

**[→ Read Sync ACP Guide](../agent_types/sync.md)**

### Async ACP

Powerful event-driven approach for complex agents. Choose between Base (learning/development) or Temporal (production).

**[→ Read Async ACP Overview](../agent_types/async/overview.md)**

---

## Additional Resources

- **[Migration Guide](../concepts/migration_guide.md)** - Upgrade from Sync to Async, or Base to Temporal

---

## Next Steps

- **New to Agentex?** Follow the [Quick Start Guide on GitHub](https://github.com/scaleapi/scale-agentex#quick-start)
- **Ready to build?** Check out [Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials)
- **Need help choosing?** Read [Choose Your Agent Type](../getting_started/choose_your_agent_type.md)
