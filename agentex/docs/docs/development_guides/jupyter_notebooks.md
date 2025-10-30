# Jupyter Notebooks for Agent Development

Jupyter Notebooks provide an excellent environment for developing and testing AgentEx agents. Every project created with `agentex init` automatically includes a `dev.ipynb` notebook, pre-configured with your agent name and ready-to-use examples for testing your agent.

!!! note "Recommended: Use Agentex UI for Local Development"
    This documentation is primarily for **local development** using notebooks or programmatic access. For most users, we recommend using the **[Agentex UI](https://github.com/scaleapi/scale-agentex/tree/main/agentex-ui){target="_blank"}** instead, as it automatically handles streaming, delta aggregation, and polling for you - so you don't have to manage these complexities yourself.

    However, if you prefer a notebook or programmatic experience, this guide will show you how to interact with your agents directly using the Python SDK.

## Prerequisites

Before starting, ensure you have:

1. **AgentEx server running locally** (see [Getting Started](https://github.com/scaleapi/scale-agentex#getting-started){target="_blank"})
2. **AgentEx Python SDK installed**: `uv tool install agentex-sdk`
3. **Your agent running**: `agentex agents run --manifest manifest.yaml`

## The `dev.ipynb` Notebook

When you run `agentex init`, a `dev.ipynb` notebook is automatically created in your project directory. This notebook is pre-configured with:

- **Client initialization** to connect to your local AgentEx server
- **Your agent name** already set (no need to manually configure)
- **Working examples** tailored to your agent type (Sync or Agentic)
- **Code snippets** demonstrating both streaming and non-streaming patterns

Simply open the notebook and run the cells to start testing your agent immediately. The examples below explain what's in the notebook and how to customize it for your needs.

## Sync ACP Agents

### Lifecycle Overview

Sync ACP agents follow a simple request-response pattern:

- **Send messages** → **Receive immediate responses**
- Messages are grouped by **tasks** (conversation sessions)
- If you don't create a task explicitly, one will be created automatically
- Responses are **synchronous** - you get them immediately after sending

### What's in the Notebook

Your `dev.ipynb` notebook for Sync ACP agents contains the following pre-configured cells:

#### Cell 1: Client Setup (Already Configured)

```python
from agentex import Agentex

# Connect to your local AgentEx server
client = Agentex(base_url="http://localhost:5003")
```

#### Cell 2: Agent Name (Already Set)

```python
AGENT_NAME = "your-agent-name"  # This is pre-filled with your actual agent name
```

#### Cell 3: (Optional) Create a Task

This cell is commented out by default since task creation is optional for Sync agents. Uncomment if you want to organize messages into a specific task:

```python
# (Optional) Create a new task. If you don't create a new task,
# each message will be sent to a new task. The server will create the task for you.

# import uuid

# TASK_ID = str(uuid.uuid4())[:8]

# rpc_response = client.agents.rpc_by_name(
#     agent_name=AGENT_NAME,
#     method="task/create",
#     params={
#         "name": f"{TASK_ID}-task",
#         "params": {}
#     }
# )

# task = rpc_response.result
# print(task)
```

#### Cell 4: Send Messages (Non-Streaming)

This cell demonstrates sending a message and receiving an immediate, complete response. Setting `stream=False` returns complete `TaskMessage` objects - the entire message is available at once with no need to accumulate deltas.

```python
# Test non streaming response
from agentex.types import TextContent

# The response is expected to be a list of TaskMessage objects, which is a union of:
# - TextContent: A message with just text content
# - DataContent: A message with JSON-serializable data content
# - ToolRequestContent: A message with a tool request (JSON-serializable)
# - ToolResponseContent: A message with a tool response

# When processing the message/send response, you can handle different content types
rpc_response = client.agents.send_message(
    agent_name=AGENT_NAME,
    params={
        "content": {"type": "text", "author": "user", "content": "Hello what can you do?"},
        "stream": False  # Returns complete TaskMessage objects
    }
)

if not rpc_response or not rpc_response.result:
    raise ValueError("No result in response")

# Extract and print just the text content from the response
for task_message in rpc_response.result:
    content = task_message.content
    if isinstance(content, TextContent):
        text = content.content
        print(text)  # Full text already available - no accumulation needed
```

#### Cell 5: Send Messages (Streaming)

This cell demonstrates streaming responses in real-time as the agent generates them. Setting `stream=True` returns incremental `TaskMessageUpdate` objects (deltas) that you must accumulate to build the complete message. This is useful for displaying responses as they're generated, providing a better user experience.

```python
# Test streaming response
from agentex.types.task_message_update import StreamTaskMessageDelta, StreamTaskMessageFull
from agentex.types.text_delta import TextDelta

# The result of message/send with stream=True is a TaskMessageUpdate, a union of:
# - StreamTaskMessageStart: Indicator that streaming started (no useful content)
# - StreamTaskMessageDelta: A delta of streaming message (contains text delta to aggregate)
# - StreamTaskMessageDone: Indicator that streaming finished (no useful content)
# - StreamTaskMessageFull: A non-streaming message (full message, not deltas)

# When processing StreamTaskMessageDelta, you can handle TextDelta, DataDelta,
# ToolRequestDelta, or ToolResponseDelta depending on what your agent returns

for agent_rpc_response_chunk in client.agents.send_message_stream(
    agent_name=AGENT_NAME,
    params={
        "content": {"type": "text", "author": "user", "content": "Hello what can you do?"},
        "stream": True  # Returns TaskMessageUpdate objects (incremental deltas)
    }
):
    # We know that the result of message/send when stream is True is TaskMessageUpdate
    task_message_update = agent_rpc_response_chunk.result
    # Print only the text deltas as they arrive or any full messages
    if isinstance(task_message_update, StreamTaskMessageDelta):
        delta = task_message_update.delta
        if isinstance(delta, TextDelta):
            # Each delta is a small piece - print immediately for real-time display
            # Note: If you need the full text, accumulate these deltas yourself
            print(delta.text_delta, end="", flush=True)
        else:
            print(f"Found non-text {type(task_message)} object in streaming message.")
    elif isinstance(task_message_update, StreamTaskMessageFull):
        content = task_message_update.content
        if isinstance(content, TextContent):
            print(content.content)
        else:
            print(f"Found non-text {type(task_message)} object in full message.")
```

## Agentic ACP Agents

### Lifecycle Overview

Agentic ACP agents work asynchronously:

- **Send events** → **Agent processes when ready** → **Subscribe to responses**
- Events are like **mobile phone notifications** - asynchronous and non-blocking
- Agents can **accumulate events** or **process immediately** based on their logic
- You must **subscribe to responses** rather than waiting for immediate replies
- **Task creation is required** for all agentic interactions

### What's in the Notebook

Your `dev.ipynb` notebook for Agentic ACP agents contains the following pre-configured cells:

#### Cell 1: Client Setup (Already Configured)

```python
from agentex import Agentex

# Connect to your local AgentEx server
client = Agentex(base_url="http://localhost:5003")
```

#### Cell 2: Agent Name (Already Set)

```python
AGENT_NAME = "your-agent-name"  # This is pre-filled with your actual agent name
```

#### Cell 3: Create a Task (Required)

For agentic agents, task creation is **required** before sending any events:

```python
# (REQUIRED) Create a new task. For Agentic agents,
# you must create a task for messages to be associated with.
import uuid

rpc_response = client.agents.create_task(
    agent_name=AGENT_NAME,
    params={
        "name": f"{str(uuid.uuid4())[:8]}-task",
        "params": {}
    }
)

task = rpc_response.result
print(task)
```

#### Cell 4: Send Events

This cell sends an event to your agent. The agent will process it asynchronously:

```python
# Send an event to the agent

# The response is expected to be a list of TaskMessage objects, which is a union of:
# - TextContent: A message with just text content
# - DataContent: A message with JSON-serializable data content
# - ToolRequestContent: A message with a tool request (JSON-serializable)
# - ToolResponseContent: A message with a tool response

# When processing the message/send response, you can handle different content types
rpc_response = client.agents.send_event(
    agent_name=AGENT_NAME,
    params={
        "content": {"type": "text", "author": "user", "content": "Hello what can you do?"},
        "task_id": task.id,
    }
)

event = rpc_response.result
print(event)
```

#### Cell 5: Subscribe to Async Responses

Since agentic agents work asynchronously, use the `subscribe_to_async_task_messages` utility to wait for and display responses:

```python
# Subscribe to the async task messages produced by the agent
from agentex.lib.utils.dev_tools import subscribe_to_async_task_messages

task_messages = subscribe_to_async_task_messages(
    client=client,
    task=task,
    only_after_timestamp=event.created_at,  # Only get messages after your event
    print_messages=True,   # Automatically print messages as they arrive
    rich_print=True,       # Use rich formatting for better readability
    timeout=5,             # Wait up to 5 seconds for responses
)
```

!!! tip "Troubleshooting Async Responses"
    If no messages appear, your agent might still be processing. Increase `timeout` or **rerun the cell** to continue polling (keep the same `only_after_timestamp`). To see all messages in the conversation, remove the `only_after_timestamp` parameter entirely.

## Understanding Response Types

All RPC methods return a response object with a `.result` field that contains the actual data:

**`send_message`:**

```python
# Non-streaming (stream=False)
rpc_response = client.agents.send_message(
    agent_name=AGENT_NAME,
    params={"content": {...}, "stream": False}
)
task_messages = rpc_response.result  # ← List[TaskMessage] - complete messages

# Each TaskMessage contains the full content
for task_message in task_messages:
    print(task_message.content)  # TextContent, DataContent, etc.
```

```python
# Streaming (stream=True)
for chunk in client.agents.send_message_stream(
    agent_name=AGENT_NAME,
    params={"content": {...}, "stream": True}
):
    task_message_update = chunk.result  # ← TaskMessageUpdate - incremental deltas

    # Handle StreamTaskMessageDelta, StreamTaskMessageFull, etc.
    if isinstance(task_message_update, StreamTaskMessageDelta):
        print(task_message_update.delta.text_delta)  # Accumulate deltas yourself
```

**Key difference:** Non-streaming returns complete `TaskMessage` objects, streaming returns `TaskMessageUpdate` deltas that you must accumulate.

**`send_event`:**
```python
rpc_response = client.agents.send_event(...)
event = rpc_response.result  # ← .result field contains the Event object

# Event has metadata: id, created_at, task_id, etc.
print(event.id)
print(event.created_at)
```

**Important:** The `Event` object is just confirmation that your event was sent - it does **not** contain the agent's response. The agent processes events asynchronously, so you must use `subscribe_to_async_task_messages()` (see Cell 5 above) to see the agent's actual responses.

**`create_task`:**
```python
rpc_response = client.agents.create_task(...)
task = rpc_response.result  # ← .result field contains the Task object

# Task has metadata: id, name, status, created_at, etc.
print(task.id)
print(task.name)
```

**`cancel_task`:**
```python
rpc_response = client.agents.cancel_task(...)
result = rpc_response.result  # ← .result field contains a dict

# Dict format: {"message": "Task {task_id} cancelled successfully"}
print(result["message"])
```
