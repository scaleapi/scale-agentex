# Choose Your Agent Type

Agentex supports three agent types with different execution models and capabilities.

## Agent Type Comparison

| Agent Type | [Sync Agents](../acp/sync.md) | [Agentic Agents (Base)](../acp/agentic/base.md) | [Agentic Agents (Temporal)](../acp/agentic/temporal.md) |
|---------|-------------|----------------|-----------------|
| **Execution Model** | Blocking, synchronous | Asynchronous, non-blocking | Asynchronous, non-blocking |
| **Concurrent Requests** | Processes one request at a time | Can process multiple concurrent requests | Can process multiple concurrent requests |
| **Handler Methods** | Single handler<br><br>`on_message_send` | Three handlers<br><br>`on_task_create`, `on_task_event_send`, `on_task_cancel` | Three handlers<br><br>`on_task_create`, `on_task_event_send`, `on_task_cancel` |
| **Data Persistence across turns** | via `adk.state` API | via `adk.state` API | Workflow class variables persist automatically<br><br>(`adk.state` API usage is optional) |
| **Message Creation** | Directly return `TaskMessageContent` objects or yield `TaskMessageUpdate` objects<br><br>Agentex automatically creates input and output message objects and automatically handles streaming | Explicitly call `adk.messages.create()` | Explicitly call `adk.messages.create()` |
| **Response Pattern** | Return value becomes agent message | All messages must be created by the agent developer via Agentex Python SDK | All messages must be created by the agent developer via Agentex Python SDK |
| **Durability** | No durability guarantees. Agent developer must handle crashes and retry idempotency. | No durability guarantees. Agent developer must handle crashes and retry idempotency. | Survives crashes and mid-execution restarts. Agent developer can use Temporal's Python SDK to handle crashes and retries natively. |
| **Best For** | Simple request-response patterns | Asynchronous workflows, stateful applications | Workflows with complex multi-step tool calls, human-in-the-loop approvals, long-running processes |
| **Example Use Cases** | FAQ bots, translation services, data lookups | Interactive applications, multi-step analysis, complex business logic | Enterprise integrations, multi-day processes, distributed coordination |
| **Typical Complexity** | ~30 lines, 1 file | ~80 lines, 1 file | 150+ lines, 4 files |

**Learn more:** [Sync ACP](../acp/sync.md) \| [Agentic ACP](../acp/agentic/overview.md) \| [Temporal Guide](../development_guides/temporal_guide.md) \| [Tutorials](../development_guides/tutorials.md)

---

## Upgrade Path

| Current Type | When to Upgrade | Upgrade To | Key Benefit |
|--------------|----------------|------------|-------------|
| **Sync** | Need to handle concurrent requests, perform long running tasks, you find yourself polling or dealing with resource contention issues. | **Agentic (Base)** | Asynchronous execution and state management |
| **Agentic (Base)** | Need workflows that survive crashes, have complex multi-step tool calls, or need human-in-the-loop approvals | **Agentic (Temporal)** | Durable execution and complex transactional reliability |

## Migration Guides

### Sync → Agentic (Base)

**What changes:**

1. Replace `@acp.on_message_send` handler with three handlers:

    - `@acp.on_task_create` - Initialize task state when task is created
    - `@acp.on_task_event_send` - Process each incoming event/message
    - `@acp.on_task_cancel` - Clean up when task is cancelled

2. Change from returning content to explicitly calling `adk.messages.create()` for all messages

3. Update ACP configuration from `acp_type="sync"` to `acp_type="agentic"` with `AgenticACPConfig(type="base")`

!!! tip
    It's probably easier just to run `agentex init` to bootstrap the skeleton of a new Agentex agent (choose `Agentic - ACP Only` when asked for the type) and then copy over the logic yourself.

**Guide:** [Migration Guide](../concepts/migration_guide.md#sync-to-agentic)

### Agentic (Base) → Agentic (Temporal)

**What changes:**

1. Create new files in your `project/` directory:

    - `workflow.py` - Contains your workflow class with `@workflow.run` and `@workflow.signal` methods
    - `activities.py` - Contains custom Temporal activities (if needed)
    - `run_worker.py` - Runs the Temporal worker process

2. Update `acp.py` - Change config from `AgenticACPConfig(type="base")` to `TemporalACPConfig(type="temporal")`

3. Move handler logic from `@acp.on_task_create`, `@acp.on_task_event_send`, `@acp.on_task_cancel` to corresponding workflow methods

4. Store state in workflow class variables (e.g., `self._state`) instead of only using `adk.state` API

!!! tip
    It's probably easier just to run `agentex init` to bootstrap the skeleton of a new Agentex agent (choose `Agentic - Temporal` when asked for the type) and then copy over the logic yourself.

**Guide:** [Migration Guide](../concepts/migration_guide.md#agentic-to-temporal)

---
