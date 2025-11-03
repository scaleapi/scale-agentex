# Migration Guide: Converting Between ACP Types

This guide provides comprehensive, step-by-step instructions for migrating agents between complexity levels as your requirements evolve. Each migration path includes real examples, common challenges, and testing strategies.

## Migration Paths Overview

| From | To | When to Migrate | Complexity Increase |
|------|----|-----------------|--------------------|
| **Sync ACP** (~30 lines) | **Base Agentic ACP** (~80 lines) | Need state management, lifecycle control | Medium |
| **Base Agentic ACP** (~80 lines) | **Temporal Agentic ACP** (~150+ lines) | Production reliability, enterprise scale | High |
| **Sync ACP** (~30 lines) | **Temporal Agentic ACP** (~150+ lines) | Direct to production (skip intermediate) | Very High |

## Part 1: Sync ACP → Base Agentic ACP

### When to Migrate

**Upgrade Triggers** - Migrate when you need:

- ✅ **Complex state management** across multiple interactions
- ✅ **Explicit lifecycle control** (initialization, cleanup)  
- ✅ **Event-driven processing** patterns
- ✅ **Resource coordination** between requests
- ✅ **Advanced debugging** and monitoring

**Warning Signs** in your Sync ACP:

- State management becoming complex with multiple `adk.state.update()` calls
- Need for initialization logic before first message
- Requirements for cleanup after task completion
- Multiple API calls that need coordination
- Growing handler function (>50 lines)

### Step-by-Step Conversion Process

#### Step 1: Create the New Handler Structure

**Before (Sync ACP)**:
```python
from agentex.sdk.fastacp.fastacp import FastACP
from agentex.types.acp import SendMessageParams
from agentex.types.task_messages import TextContent, MessageAuthor

acp = FastACP.create(acp_type="sync")

@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # Your existing logic here
    response = await process_message(params.content.content)
    return TextContent(author=MessageAuthor.AGENT, content=response)
```

**After (Base Agentic ACP)**:
```python
from agentex.sdk.fastacp.fastacp import FastACP
from agentex.types.acp import CreateTaskParams, SendEventParams, CancelTaskParams
from agentex.types.task_messages import TextContent, MessageAuthor
from agentex import adk

acp = FastACP.create(
    acp_type="agentic",
    acp_config=AgenticACPConfig(acp_type="base")
)

@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    # Initialize state (new in Agentic)
    await adk.state.create(
        task_id=params.task.id,
        agent_id=params.agent.id,
        state={"initialized": True, "message_count": 0}
    )

@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Your migrated logic here
    if params.event.content:
        response = await process_message(params.event.content.content)
        
        # Must manually create messages (new requirement)
        await adk.messages.create(
            task_id=params.task.id,
            content=TextContent(author=MessageAuthor.AGENT, content=response)
        )

@acp.on_task_cancel
async def handle_task_cancel(params: CancelTaskParams):
    # Cleanup logic (new in Agentic)
    await cleanup_resources(params.task.id)
```

#### Step 2: Handle State Migration

**Key Changes**:

1. **State Initialization**: Move any setup logic to `on_task_create`
2. **Message Creation**: Manually create all messages with `adk.messages.create()`
3. **State Updates**: Update state in `on_task_event_send` as needed
4. **Resource Cleanup**: Add cleanup logic in `on_task_cancel`

### Example: Chat Bot Migration

**Original Sync ACP (35 lines)**:
```python
from agentex.sdk.fastacp.fastacp import FastACP
from agentex.types.acp import SendMessageParams
from agentex.types.task_messages import TextContent, MessageAuthor
from agentex import adk

acp = FastACP.create(acp_type="sync")

@acp.on_message_send
async def handle_message_send(params: SendMessageParams) -> TextContent:
    """Simple chatbot with conversation history"""
    
    # Get conversation history
    messages = await adk.messages.list(task_id=params.task.id)
    conversation_context = build_conversation_context(messages)
    
    # Generate response
    response = await generate_ai_response(
        user_input=params.content.content,
        context=conversation_context
    )
    
    return TextContent(
        author=MessageAuthor.AGENT,
        content=response
    )

def build_conversation_context(messages):
    """Helper function - stays the same"""
    return [msg.content.content for msg in messages[-5:]]

async def generate_ai_response(user_input, context):
    """Helper function - stays the same"""
    return f"You said: {user_input}. Context: {len(context)} previous messages"
```

**Migrated Base Agentic ACP (85 lines)**:
```python
from agentex.sdk.fastacp.fastacp import FastACP
from agentex.types.acp import CreateTaskParams, SendEventParams, CancelTaskParams
from agentex.types.task_messages import TextContent, MessageAuthor
from agentex.types.fastacp import AgenticACPConfig
from agentex import adk

acp = FastACP.create(
    acp_type="agentic",
    acp_config=AgenticACPConfig(acp_type="base")
)

@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    """Initialize conversation state"""
    
    await adk.state.create(
        task_id=params.task.id,
        agent_id=params.agent.id,
        state={
            "conversation_started": True,
            "total_messages": 0,
            "user_preferences": {}
        }
    )
    
    # Send welcome message
    await adk.messages.create(
        task_id=params.task.id,
        content=TextContent(
            author=MessageAuthor.AGENT,
            content="Hello! I'm ready to chat. How can I help you today?"
        )
    )

@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    """Process conversation events with enhanced state tracking"""
    
    if not params.event.content:
        return
        
    # Update state
    current_state = await adk.state.get(task_id=params.task.id)
    current_state["total_messages"] += 1
    await adk.state.update(
        task_id=params.task.id,
        state=current_state
    )
    
    # Get conversation history (same logic as before)
    messages = await adk.messages.list(task_id=params.task.id)
    conversation_context = build_conversation_context(messages)
    
    # Generate response (same logic as before)
    response = await generate_ai_response(
        user_input=params.event.content.content,
        context=conversation_context,
        state=current_state  # Now we can pass state!
    )
    
    # Manually create response message (new requirement)
    await adk.messages.create(
        task_id=params.task.id,
        content=TextContent(
            author=MessageAuthor.AGENT,
            content=response
        )
    )

@acp.on_task_cancel
async def handle_task_cancel(params: CancelTaskParams):
    """Clean up conversation resources"""
    
    # Log conversation summary
    state = await adk.state.get(task_id=params.task.id)
    print(f"Conversation ended. Total messages: {state.get('total_messages', 0)}")
    
    # Could add: save conversation to database, cleanup external resources, etc.

# Helper functions (mostly unchanged)
def build_conversation_context(messages):
    """Helper function - same as before"""
    return [msg.content.content for msg in messages[-5:]]

async def generate_ai_response(user_input, context, state=None):
    """Enhanced helper function - now uses state"""
    message_count = state.get('total_messages', 0) if state else 0
    return f"You said: {user_input}. Context: {len(context)} previous messages. Session: {message_count} total messages"
```

**Key Migration Changes**:

1. **Handler Structure**: 1 handler → 3 handlers
2. **State Management**: Optional → Required initialization
3. **Message Creation**: Automatic → Manual with `adk.messages.create()`
4. **Lifecycle Control**: None → Explicit create/cancel handlers
5. **Enhanced Capabilities**: Can now track conversation state, send welcome messages, cleanup resources

## Part 2: Base Agentic ACP → Temporal Agentic ACP

### When to Migrate

**Upgrade Triggers** - Migrate when you need:

- ✅ **Production reliability** with automatic retries
- ✅ **Long-running workflows** (hours, days, weeks)
- ✅ **Enterprise-grade durability** that survives restarts
- ✅ **Complex state coordination** across multiple activities
- ✅ **Guaranteed execution** with distributed processing

**Warning Signs** in your Base Agentic ACP:

- Manual retry logic becoming complex
- State coordination across multiple async operations
- Need for workflow persistence across server restarts
- Requirements for enterprise SLAs and reliability
- Complex error handling and recovery scenarios

### Step-by-Step Conversion Process

#### Step 1: Create Temporal Workflow Structure

**Before (Base Agentic ACP)**:
```python
acp = FastACP.create(
    acp_type="agentic",
    acp_config=AgenticACPConfig(acp_type="base")
)

@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    await adk.state.create(task_id=params.task.id, agent_id=params.agent.id, state={})

@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Process events directly
    result = await some_api_call(params.event.content)
    await adk.messages.create(task_id=params.task.id, content=result)
```

**After (Temporal Agentic ACP)**:
```python
from temporalio import workflow, activity
from agentex.core.temporal.workflow import AgentexWorkflow

acp = FastACP.create(
    acp_type="agentic",
    acp_config=AgenticACPConfig(acp_type="temporal")
)

@workflow.defn
class MyAgentWorkflow(AgentexWorkflow):
    def __init__(self):
        super().__init__()
        self.state = {"initialized": False}
    
    @workflow.run
    async def run_workflow(self, params):
        # Workflow orchestration logic
        await workflow.execute_activity(
            initialize_agent,
            params,
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        # Process events through activities
        async for event in self.events():
            result = await workflow.execute_activity(
                process_event_activity,
                event,
                start_to_close_timeout=timedelta(minutes=5)
            )

@activity.defn
async def initialize_agent(params):
    """Temporal activity - automatically retried"""
    await adk.state.create(task_id=params.task.id, agent_id=params.agent.id, state={})

@activity.defn  
async def process_event_activity(event):
    """Temporal activity - automatically retried"""
    result = await some_api_call(event.content)
    await adk.messages.create(task_id=event.task.id, content=result)
    return result

@acp.workflow(MyAgentWorkflow)
async def workflow_handler():
    return MyAgentWorkflow()
```

#### Step 2: Wrap Operations in Activities

**Key Principle**: Any operation that could fail or has side effects should be wrapped in a Temporal activity.

**Before (Direct calls)**:
```python
# Direct API calls (can fail, no retries)
result = await external_api.call(data)
await database.save(result)
await send_notification(result)
```

**After (Temporal activities)**:
```python
# Wrapped in activities (automatic retries, durability)
result = await workflow.execute_activity(
    external_api_activity,
    data,
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(maximum_attempts=3)
)

await workflow.execute_activity(
    database_save_activity,
    result,
    start_to_close_timeout=timedelta(seconds=30)
)

await workflow.execute_activity(
    notification_activity,
    result,
    start_to_close_timeout=timedelta(seconds=10)
)
```

**Key Migration Benefits**:

1. **Automatic Retries**: All activities retry automatically on failure
2. **Durable State**: Workflow state persists across server restarts
3. **Enterprise Reliability**: Guaranteed execution with Temporal's durability
4. **Complex Orchestration**: Easy to coordinate multiple activities
5. **Fault Tolerance**: Comprehensive error handling and recovery

## Common Migration Challenges & Solutions

### Challenge 1: State Management Changes

**Problem**: Different state APIs between ACP types

**Solution**: Create adapter functions:
```python
# Migration helper
async def migrate_state(task_id: str, from_type: str, to_type: str):
    if from_type == "sync" and to_type == "agentic":
        # Sync uses automatic state, Agentic needs explicit creation
        existing_messages = await adk.messages.list(task_id=task_id)
        initial_state = {"migrated_message_count": len(existing_messages)}
        await adk.state.create(task_id=task_id, state=initial_state)
```

### Challenge 2: Message Creation Differences

**Problem**: Sync auto-creates messages, Agentic requires manual creation

**Solution**: Create message creation helpers:
```python
# Migration helper
async def create_agent_message(task_id: str, content: str):
    """Standardized message creation for migrations"""
    await adk.messages.create(
        task_id=task_id,
        content=TextContent(author=MessageAuthor.AGENT, content=content)
    )
```

---

## Summary

Migration between ACP types follows clear patterns. Test your migrated agent with the same inputs to ensure equivalent behavior before deploying to production. 