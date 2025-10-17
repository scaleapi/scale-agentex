# TaskMessage Concepts

TaskMessages represent individual messages within a conversation or workflow. They're the building blocks of communication between clients and agents in Agentex.

## What is a TaskMessage?

A **TaskMessage** is a single unit of communication within a task. Every message contains:

- **Content**: The actual message data (text, structured data, tool calls, etc.)
- **Metadata**: Author, timestamps, and message identification
- **Relationships**: Links to the parent task and conversation context

Think of TaskMessages like individual chat messages, API responses, tool executions, or workflow steps.

!!! warning "Important: TaskMessages vs LLM Messages"
    
    **Agentex stores conversation history as `TaskMessages`, not LLM-compatible messages.** This might seem duplicative, but the split between TaskMessage and LLMMessage is intentional and important.

    **TaskMessages** are messages that are sent between an Agent and a Client. They are fundamentally decoupled from messages sent to the LLM. This is because you may want to send additional metadata to allow the client to render the message on the UI differently.

    **LLMMessages** are OpenAI-compatible messages that are sent to the LLM, and are used to track the state of a conversation with a model.

    In simple scenarios your conversion logic will just use the default converters. However, in complex scenarios where you are leveraging the flexibility of the TaskMessage type to send non-LLM-specific metadata, you should write custom conversion logic.

    **Some complex scenarios include:**

    - Taking a markdown document output by an LLM, postprocessing it into a JSON object to clearly denote title, content, and footers. This can be sent as a `DataContent` TaskMessage to the client and converted back to markdown here to send back to the LLM.
    - If using multiple LLMs (like in an actor-critic framework), you may want to send `DataContent` that denotes which LLM generated which part of the output and write conversion logic to split the TaskMessage history into multiple LLM conversations.
    - If using multiple LLMs, but one LLM's output should not be sent to the user (i.e. a critic model), you can leverage the State as an internal storage mechanism to store the critic model's conversation history. This is a powerful and flexible way to handle complex scenarios.

## Message Content Types

TaskMessages use polymorphic content - each message can contain different types of data:

### TextContent - Human Communication

For natural language interactions:

```python
from agentex.types.text_content import TextContent
from agentex.types.message_author import MessageAuthor
from agentex.types.text_content import TextFormat

# Simple text message
text_msg = TextContent(
    author=MessageAuthor.AGENT,
    content="Hello! How can I help you today?",
    format=TextFormat.PLAIN
)

# Formatted text (markdown)
formatted_msg = TextContent(
    author=MessageAuthor.AGENT,
    content="Here's your **analysis**:\n\n- Point 1\n- Point 2",
    format=TextFormat.MARKDOWN
)

# Text with file attachments
msg_with_files = TextContent(
    author=MessageAuthor.AGENT,
    content="I've attached the report you requested.",
    attachments=[
        FileAttachment(
            name="report.pdf",
            url="https://example.com/files/report.pdf",
            mime_type="application/pdf"
        )
    ]
)
```

### DataContent - Structured Data

For API responses, analytics, or structured information:

```python
from agentex.types.data_content import DataContent

# API response data
api_response = DataContent(
    author=MessageAuthor.AGENT,
    data={
        "status": "success",
        "results": [
            {"id": 1, "name": "Item 1", "score": 0.95},
            {"id": 2, "name": "Item 2", "score": 0.87}
        ],
        "total_count": 2
    }
)

# Analysis results
analysis_result = DataContent(
    author=MessageAuthor.AGENT,
    data={
        "sentiment": "positive",
        "confidence": 0.92,
        "keywords": ["excellent", "satisfied", "recommend"],
        "summary": "Customer feedback is overwhelmingly positive"
    }
)
```

### ToolRequestContent - Tool Execution

For requesting tool/function execution:

```python
from agentex.types.tool_request_content import ToolRequestContent

# Request weather information
weather_request = ToolRequestContent(
    author=MessageAuthor.AGENT,
    tool_call_id="123",
    name="get_weather",
    arguments={
        "location": "San Francisco, CA",
        "units": "celsius"
    }
)

# Request database query
db_request = ToolRequestContent(
    author=MessageAuthor.AGENT,
    tool_call_id="123",
    name="query_database",
    arguments={
        "table": "users",
        "filters": {"status": "active"},
        "limit": 100
    }
)
```

### ToolResponseContent - Tool Execution Results

For returning tool execution results:

```python
from agentex.types.tool_response_content import ToolResponseContent

# Request weather information
weather_request = ToolRequestContent(
    author=MessageAuthor.AGENT,
    tool_call_id="123",
    name="get_weather",
    arguments={
        "location": "San Francisco, CA",
        "units": "celsius"
    }
)

# Response with weather data
weather_response = ToolResponseContent(
    author=MessageAuthor.AGENT,
    tool_call_id="123",
    name="get_weather",
    result={
        "temperature": 22.5,
        "description": "Sunny with a chance of clouds"
    }
)
```


## Message Lifecycle

### Creation

**Most messages are sent by external clients** (web applications, API calls, mobile apps), but **agents can also create messages directly** through the ADK. Direct creation is most common for:

- **Echoing back user messages** for confirmation or clarification
- **Creating agent responses** in complex workflows  
- **Sending tool requests** to external systems
- **Returning tool responses** with execution results

```python
# Create and send a message directly through ADK
new_message = await adk.messages.create(
    task_id=task_id,
    content=TextContent(
        author=MessageAuthor.AGENT,
        content="Your request has been processed successfully!"
    )
)

print(f"Created message {new_message.id} at {new_message.created_at}")

# Common patterns for different content types
await adk.messages.create(
    task_id=task_id,
    content=ToolRequestContent(
        author=MessageAuthor.AGENT,
        tool_call_id="abc123",
        name="search_database",
        arguments={"query": "user data", "limit": 10}
    )
)
```

!!! warning "Sending Messages to Agents"
    
    If you want to **send a message directly to an agent** (not just create it in the task ledger), use the appropriate ACP function:
    
    - **Sync ACP**: Use `adk.acp.send_message()` to trigger the agent's `@acp.on_message_send` handler
    - **Agentic ACP**: Use `adk.acp.send_event()` to trigger the agent's `@acp.on_task_event_send` handler
    
    Simply using `adk.messages.create()` only adds the message to the task ledger - it doesn't notify or trigger the agent to process it.

### Retrieval

Get conversation history:

```python
# Get all messages in a task
all_messages = await adk.messages.list(task_id=task_id)

# Process conversation history
for message in all_messages:
    author = message.content.author
    timestamp = message.created_at
    
    if message.content.type == TaskMessageContentType.TEXT:
        print(f"[{timestamp}] {author}: {message.content.content}")
    elif message.content.type == TaskMessageContentType.DATA:
        print(f"[{timestamp}] {author}: Data - {message.content.data}")
```

### Message Processing

Handle different content types:

* **TextContent**: Human-readable text messages
* **DataContent**: Structured data
* **ToolRequestContent**: Tool execution requests
* **ToolResponseContent**: Tool execution results

!!! note "Conversion to LLM Messages"
    
    Sometimes you may want to convert a TaskMessage to an LLM-compatible message. You can explicitly do this by using the `sdk.messages.convert_to_llm_messages` function.

    ```python
    from agentex.lib.sdk.utils.messages import convert_task_messages_to_llm_messages

    llm_messages = convert_task_messages_to_llm_messages(task_message)
    ```

    ::: agentex.lib.sdk.utils.messages.convert_task_messages_to_llm_messages
        options:
            show_root_heading: true
            show_root_toc_entry: false


## API Reference

For complete type definitions, see the [API - Types Reference](../api/types.md)
