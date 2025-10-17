# Jupyter Notebooks for Agent Development

Jupyter Notebooks provide an excellent environment for developing and testing AgentEx agents. This guide will walk you through how to use notebooks effectively for both **Sync ACP** and **Agentic ACP** agents.

## Prerequisites

Before starting, ensure you have:

1. **AgentEx server running locally** (see [Quick Start](../tutorials.md))
2. **AgentEx Python SDK installed**: `pip install agentex-sdk`
3. **Your agent running**: `agentex agents run --manifest manifest.yaml`

## Sync ACP Agents

### Lifecycle Overview

Sync ACP agents follow a simple request-response pattern:

- **Send messages** → **Receive immediate responses**
- Messages are grouped by **tasks** (conversation sessions)
- If you don't create a task explicitly, one will be created automatically
- Responses are **synchronous** - you get them immediately after sending

### Setting Up Your Notebook

Start by initializing the AgentEx client and setting your agent name:

```python
from agentex import Agentex

# Connect to your local AgentEx server
client = Agentex(base_url="http://localhost:5003")

# Set your agent name (replace with your actual agent name)
AGENT_NAME = "your-agent-name"
```

### Step 1: (Optional) Create a Task

For sync agents, task creation is optional but recommended for organizing conversations:

```python
# Create a new task with a descriptive name
rpc_response = client.agents.create_task(
    agent_name=AGENT_NAME,
    params={
        "name": "my-chat-session-123",  # Use any descriptive name
        "params": {}  # Optional task parameters
    }
)

task = rpc_response.result
print(f"Created task: {task.id}")
```

### Step 2: Send Messages (Non-Streaming)

Send messages and receive immediate responses:

```python
# Send a message to your agent
rpc_response = client.agents.send_message(
    agent_name=AGENT_NAME,
    params={
        "content": {
            "type": "text", 
            "author": "user", 
            "content": "Hello! What can you do?"
        },
        "stream": False  # Non-streaming response
    }
)

# Process the response - returns List[TaskMessage]
if rpc_response and rpc_response.result:
    for task_message in rpc_response.result:
        content = task_message.content
        # Process each type of content here (text, data, tool requests, etc.)
        print(f"Agent response: {content}")
```

### Step 3: Send Messages (Streaming)

For real-time streaming responses:

```python
# Send a streaming message
for agent_rpc_response_chunk in client.agents.send_message_stream(
    agent_name=AGENT_NAME,
    params={
        "content": {
            "type": "text", 
            "author": "user", 
            "content": "Tell me a story about AI"
        },
        "stream": True  # Enable streaming
    }
):
    # Process streaming response - returns TaskMessageUpdate
    task_message_update = agent_rpc_response_chunk.result
    
    # Process each type of streaming update here (deltas, full messages, etc.)
    print(f"Streaming update: {task_message_update}")
```

## Agentic ACP Agents

### Lifecycle Overview

Agentic ACP agents work asynchronously:

- **Send events** → **Agent processes when ready** → **Subscribe to responses**
- Events are like **mobile phone notifications** - asynchronous and non-blocking
- Agents can **accumulate events** or **process immediately** based on their logic
- You must **subscribe to responses** rather than waiting for immediate replies
- **Task creation is required** for all agentic interactions

### Setting Up Your Notebook

```python
from agentex import Agentex

# Connect to your local AgentEx server
client = Agentex(base_url="http://localhost:5003")

# Set your agent name
AGENT_NAME = "your-agentic-agent-name"
```

### Step 1: Create a Task (Required)

For agentic agents, you **must** create a task first:

```python
# Create a new task (REQUIRED for agentic agents)
rpc_response = client.agents.create_task(
    agent_name=AGENT_NAME,
    params={
        "name": "my-workflow-session-456",  # Use any descriptive name
        "params": {}  # Optional task parameters
    }
)

task = rpc_response.result
print(f"Created task: {task.id}")
```

### Step 2: Send Events

Send events to your agent (these are asynchronous):

```python
# Send an event to your agent
rpc_response = client.agents.send_event(
    agent_name=AGENT_NAME,
    params={
        "content": {
            "type": "text", 
            "author": "user", 
            "content": "Hello! What can you do?"
        },
        "task_id": task.id,  # Associate with the task
    }
)

event = rpc_response.result
print(f"Sent event: {event.id}")
```

### Step 3: Subscribe to Async Responses

Since agentic agents work asynchronously, you need to subscribe to responses:

```python
from agentex.lib.utils.dev_tools import subscribe_to_async_task_messages

# Subscribe to task messages that arrive after your event
task_messages = subscribe_to_async_task_messages(
    client=client,
    task=task, 
    only_after_timestamp=event.created_at,  # Only get messages after your event
    print_messages=True,  # Automatically print messages as they arrive
    rich_print=True,      # Use rich formatting for better readability
    timeout=30,           # Wait up to 30 seconds for responses
)
```

## RPC Response Types

### Send Message Response Types

When using `send_message`, the response type depends on the `stream` parameter:

**Non-streaming (`stream=False`):**

- Returns: `List[TaskMessage]`
- Each `TaskMessage` contains content that can be:
  - `TextContent` - Plain text messages
  - `DataContent` - JSON-serializable data
  - `ToolRequestContent` - Tool call requests
  - `ToolResponseContent` - Tool call responses

**Streaming (`send_message_stream`):**

- Returns: `AsyncIterator[TaskMessageUpdate]`
- Each `TaskMessageUpdate` can be:
  - `StreamTaskMessageStart` - Indicates streaming started
  - `StreamTaskMessageDelta` - Contains text/data deltas to aggregate
  - `StreamTaskMessageDone` - Indicates streaming finished
  - `StreamTaskMessageFull` - Complete non-streaming message

### Send Event Response Types

When using `send_event`:

- Returns: `Event`
- Contains event metadata including `id`, `created_at`, `task_id`, etc.

### Create Task Response Types

When using `create_task`:

- Returns: `Task`
- Contains task metadata including `id`, `name`, `status`, `created_at`, etc.

### Cancel Task Response Types

When using `cancel_task`:

- Returns: `dict` with success message
- Format: `{"message": "Task {task_id} cancelled successfully"}`

## Advanced Patterns

### Working with Different Content Types

Both sync and agentic agents support various content types:

```python
# Text content (most common)
text_content = {
    "type": "text",
    "author": "user", 
    "content": "Hello world"
}

# Data content (JSON-serializable)
data_content = {
    "type": "data",
    "author": "user",
    "content": {"key": "value", "number": 42}
}

# Tool request content
tool_request_content = {
    "type": "tool_request",
    "author": "agent",
    "tool_call_id": "abc123",
    "name": "search_database",
    "arguments": {"query": "user data"}
}

# Tool response content
tool_response_content = {
    "type": "tool_response",
    "author": "agent", 
    "tool_call_id": "abc123",
    "content": {"results": ["data1", "data2"]}
}
```
