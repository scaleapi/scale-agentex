# Agent-to-Client Protocol (ACP)

The Agent-to-Client Protocol (ACP) is the foundation of how agents communicate with clients in Agentex. Understanding ACP is essential for building effective agents and choosing the right architecture for your use case. It specifies:

- **Standard message formats** for agent interactions into [`TaskMessage`](https://github.com/scaleapi/scale-agentex-python/blob/main/src/agentex/types/task_message.py) objects
- **Decorated functions** that agents must implement as entrypoints to agent logic
    - Sync ACP: [`on_message_send`](https://github.com/scaleapi/scale-agentex-python/blob/main/src/agentex/lib/sdk/fastacp/base/base_acp_server.py#L346)
    - Async ACP: [`on_task_create`](https://github.com/scaleapi/scale-agentex-python/blob/main/src/agentex/lib/sdk/fastacp/base/base_acp_server.py#L314), [`on_task_event_send`](https://github.com/scaleapi/scale-agentex-python/blob/main/src/agentex/lib/sdk/fastacp/base/base_acp_server.py#L321), [`on_task_cancel`](https://github.com/scaleapi/scale-agentex-python/blob/main/src/agentex/lib/sdk/fastacp/base/base_acp_server.py#L339)
- **Lifecycle management** for conversations and workflows
- **Streaming and communication** between clients and agents

Think of ACP as the "language" that agents and clients use to understand each other.

---

## Agent Types Overview

Agentex supports three agent types with different execution models and capabilities. Read the [Choose Your Agent Type](../getting_started/choose_your_agent_type.md) guide for a detailed comparison.

### Quick Decision Guide

**Use Sync Agents when:**

- Simple request-response patterns
- Blocking, synchronous execution is acceptable
- Processing one request at a time is sufficient

**Use Async Agents (Base) when:**

- Asynchronous workflows and stateful applications needed
- Must handle multiple concurrent requests
- Need explicit control over message creation and state

This is not a one-way door decision, to migrate from one ACP type to another, simply follow our [Agent Type Migration Guide](../agent_types/agent_type_migration_guide.md).