# Sync ACP

**Sync ACP** provides the simplest way to build agents in Agentex. Perfect for chat bots and simple question-answer interactions where you don't need complex state management or workflow control.

## Core Characteristics

- **Single handler method**: `@acp.on_message_send`
- **Automatic task lifecycle management** - Tasks created and managed automatically
- **Direct message processing** - Respond to messages immediately
- **Automatic message management** - Agentex Server creates messages on your behalf
- **Minimal complexity** - Focus on your business logic

## Message Flow

```mermaid
sequenceDiagram
    participant Client
    participant Agentex
    participant Agent

    Client->>Agentex: Send Message
    Agentex->>Agentex: Auto-create Task
    Agentex->>Agent: on_message_send(params)
    Agent->>Agent: Process Message
    Agent-->>Agentex: Return Response
    Agentex-->>Client: Response
    Note over Agentex: Task remains open for future messages
```

## Basic Implementation

```python
from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.acp import SendMessageParams
from agentex.types.text_content import TextContent
from agentex.types.message_author import MessageAuthor

# Create Sync ACP server
acp = FastACP.create(acp_type="sync")

@acp.on_message_send
async def handle_message(params: SendMessageParams):
    """Process incoming messages and return responses"""

    # Access the user's message
    user_message = params.content.content

    # Process and create response
    response_text = f"You said: {user_message}"

    # Return response (Agentex auto-creates the message)
    return TextContent(
        author=MessageAuthor.AGENT,
        content=response_text
    )
```

## Handler Parameters

### SendMessageParams

The `@acp.on_message_send` handler receives:

::: agentex.lib.types.acp.SendMessageParams
    options:
      heading_level: 4
      show_root_heading: false
      show_source: false

## When to Use Sync ACP

### Perfect For:

✅ **Simple Chat Bots**

- Customer support chatbots
- FAQ agents
- Information lookup services

✅ **Stateless Operations**

- Translation services
- Quick calculations
- Data formatting

✅ **Direct Q&A**

- Knowledge base queries
- Simple recommendations
- Status checks

### Not Ideal For:

❌ **Multi-step workflows** - Use Agentic ACP
❌ **Complex state management** - Limited state tracking
❌ **Resource coordination** - No initialization/cleanup hooks
❌ **Long-running processes** - Better suited for quick responses

## Best Practices

- **Keep handlers simple** - Sync ACP is for straightforward logic
- **Handle errors gracefully** - Return error messages to users
- **Use optional state sparingly** - For simple session data only
- **Consider migration** - Switch to Agentic ACP as complexity grows

---

## Next Steps

- **Need more complexity?** Learn about [Agentic ACP](agentic/overview.md)
- **Ready to upgrade?** See the [Migration Guide](../concepts/migration_guide.md)
- **New to Agentex?** Follow the [Quick Start Guide on GitHub](https://github.com/scaleapi/agentex#quick-start)
- **Ready to build?** Check out [Sync ACP Tutorials on GitHub](https://github.com/scaleapi/agentex-python/tree/main/examples/tutorials/00_sync)
