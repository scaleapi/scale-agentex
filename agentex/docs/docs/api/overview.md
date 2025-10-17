# API Reference Overview

This section provides comprehensive reference documentation for all Agentex types, classes, and interfaces. Use this as your definitive guide to understanding the objects and APIs you'll work with when building agents.

## What You'll Find

- **[Agent Development Kit](adk.md)** - SDK reference specifically for agent development functionswith detailed function signatures
- **[Types](types.md)** - Complete API reference for all core data types (Task, TaskMessage, Event, ACP params, etc.)

## Core Object Categories

### Task Management Objects

- **Task** - Central entity representing a conversation or workflow
- **TaskMessage** - Individual messages within tasks
- **Event** - Client actions sent to tasks
- **State** - Persistent task-specific data storage

### ACP Protocol Objects

- **ACP Parameters** - Method parameters for different ACP handlers
- **Message Content Types** - Polymorphic content system for diverse message types
- **Message Updates** - Streaming message delivery system

### Configuration Objects

- **ACP Configurations** - Settings for different ACP types (Sync, Agentic Base, Temporal)
- **LLM Configurations** - Settings for language model integrations
- **Agent Configurations** - Agent deployment and runtime settings

## Quick Reference

### Most Commonly Used Types

```python
# Essential imports for most agents
from agentex.types.task_message_content import TaskMessageContent
from agentex.types.text_content import TextContent
from agentex.types.message_author import MessageAuthor
from agentex.lib.types.acp import SendMessageParams, CreateTaskParams, SendEventParams
from agentex.types.task import Task
from agentex.types.event import Event
```

### Type Hierarchy

```
TaskMessageContent (Union Type)
├── TextContent
├── DataContent
├── ToolRequestContent
├── ToolResponseContent

ACP Parameters
├── CreateTaskParams
├── SendMessageParams
├── SendEventParams
└── CancelTaskParams

TaskMessageUpdate (Union Type)
├── StreamTaskMessageStart
├── StreamTaskMessageDelta
├── StreamTaskMessageFull
└── StreamTaskMessageDone
```

## Usage Patterns

### Type Checking

```python
from agentex.types.task_message_content import TaskMessageContent as TaskMessageContentType

# Check message content type
if params.event.content.type == TaskMessageContentType.TEXT:
    text_content = params.event.content  # TypeScript-style narrowing
    process_text(text_content.content)
elif params.event.content.type == TaskMessageContentType.DATA:
    data_content = params.event.content
    process_data(data_content.data)
```

### Creating Objects

```python
# Create a text message
message = TextContent(
    author=MessageAuthor.AGENT,
    content="Hello! How can I help you?",
    format=TextFormat.PLAIN
)

# Create structured data message
data_message = DataContent(
    author=MessageAuthor.AGENT,
    data={"result": "success", "value": 42}
)

# Create tool request message
tool_request_message = ToolRequestContent(
    author=MessageAuthor.AGENT,
    tool_call_id="123",
    name="search_knowledge_base",
    arguments={"query": "product updates", "max_results": 5}
)

# Create tool response message
tool_response_message = ToolResponseContent(
    author=MessageAuthor.AGENT,
    tool_call_id="123",
    name="search_knowledge_base",
    content="Here are the search results: [1, 2, 3]"
)
```

### Validation

All objects use Pydantic for validation:

```python
from pydantic import ValidationError

try:
    message = TextContent(
        author=MessageAuthor.AGENT,
        content="Valid message"
    )
except ValidationError as e:
    print(f"Validation failed: {e}")
```

## Navigation Guide

- **New to Agentex?** Start with [Concepts](../concepts/task.md) to understand core concepts, then check [Types](types.md) for API details
- **Looking for specific functions?** Check the [Agent Development Kit](adk.md) reference
- **Need examples?** See the [Tutorials](../tutorials.md) section
- **Advanced patterns?** Explore [Advanced Concepts](../concepts/callouts/overview.md) like race conditions and state management

## Common Patterns

### Working with Polymorphic Types

Many Agentex types are polymorphic (union types) that can be one of several variants:

```python
# TaskMessageContent is polymorphic - check the type first
content = params.event.content

if content.type == TaskMessageContentType.TEXT:
    # content is now typed as TextContent
    text = content.content
    format = content.format
elif content.type == TaskMessageContentType.DATA:
    # content is now typed as DataContent
    data = content.data
```

### Async/Await Patterns

All ADK operations are async:

```python
# Always use await with ADK operations
message = await adk.messages.create(task_id=task_id, content=content)
state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id=agent_id)
```

## Next Steps

Ready to dive into the details? Start with **[Concepts](../concepts/task.md)** to understand core concepts, then explore **[Types](types.md)** for complete API reference. 