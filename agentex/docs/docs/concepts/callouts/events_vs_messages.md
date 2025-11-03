# Events vs Messages

!!! danger "Critical for Agentic ACP"
    **Events and TaskMessages serve different purposes and are stored in separate database tables.** This distinction is fundamental to understanding how Agentic ACP works.

## The Core Distinction

| **Events** | **TaskMessages** |
|------------|------------------|
| ✅ **Stored persistently** in events table | ✅ **Stored persistently** in messages table |
| 🔄 **Agent processing notifications** | 💬 **User-facing conversation history** |
| ✅ **Can be queried** for processing | ✅ **Can be retrieved** for conversation context |
| 🚀 **Written to DB BEFORE ACP delivery** | 📝 **Created by agents or users directly** |

## Understanding the Relationship

### Events Are "Processing Queue" Items

Think of events like **work items** in a processing queue:

```python
# Event = "Work item ready for processing"
# - Stored persistently in events table
# - Contains processing context and metadata
# - Written to database BEFORE being sent to agent
# - Can be queried and tracked for processing progress

@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # This event was already saved to DB before reaching here
    event = params.event  # ✅ Persistent in events table
    
    # You can query all events for this task/agent
    all_events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id
    )  # ✅ All processing history available
    
    # TaskMessages are the user-facing conversation
    messages = await adk.messages.list(task_id=params.task.id)  # ✅ Conversation context
```

### TaskMessages Are the "User Conversation"

```python
# TaskMessage = User-facing conversation history
# - Permanently stored in messages table
# - Contains conversation content for users/clients
# - Can be retrieved anytime for chat history
# - Forms the visible conversation thread

# Access user-facing conversation history
task_messages = await adk.messages.list(task_id=task_id)
for message in task_messages:
    print(f"User sees: {message.content}")

# Events are for agent processing coordination
events = await adk.events.list_events(task_id=task_id, agent_id=agent_id)
for event in events:
    print(f"Agent processes: {event.id} at sequence {event.sequence_id}")
```

## Event Processing Patterns

### ❌ Don't Process Only Current Event Content

```python
# WRONG: Only processing the single event content
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    if params.event.content:
        # Only processing the current event content
        user_message = params.event.content.content
        response = await process_message(user_message)
        # Missing: No context from conversation history or other events!
```

### ✅ Use Events for Coordination, Process with Full Context

```python
# CORRECT: Event triggers processing, get full context from both sources
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Event tells us "work is ready to be processed"
    # (This event is already stored in DB before reaching here)
    event = params.event
    
    # Get conversation context from TaskMessages
    conversation_messages = await adk.messages.list(task_id=params.task.id)
    
    # Get processing context from Events (for coordination)
    all_events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    # Process with full context from both sources
    response = await process_with_context(conversation_messages, all_events)
    
    # Create new message for user conversation
    await adk.messages.create(
        task_id=params.task.id,
        content=TextContent(
            author=MessageAuthor.AGENT,
            content=response
        )
    )
```

## Why This Architecture Exists

### Separation of Concerns: Processing vs Conversation

The dual-table architecture enables powerful patterns:

1. **Events Table**: Tracks agent processing state and coordination
2. **Messages Table**: Maintains user-facing conversation history

### Enables Flexible Processing Strategies

```python
# Strategy 1: Process events immediately
@acp.on_task_event_send
async def immediate_processing(params: SendEventParams):
    # React to each event as it arrives
    # Events are already in DB for coordination
    response = await quick_response(params.event.content)

# Strategy 2: Batch process accumulated events
@acp.on_task_event_send  
async def batch_processing(params: SendEventParams):
    # Get current processing cursor from agent task tracker
    tracker = await adk.agent_task_tracker.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    # Get all unprocessed events since last cursor
    unprocessed_events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id,
        last_processed_event_id=tracker.last_processed_event_id,
        limit=100
    )
    
    if len(unprocessed_events) >= 5:  # Process batch of 5
        await process_event_batch(unprocessed_events)
        
        # Update cursor to track progress - ONLY after processing is complete
        await adk.agent_task_tracker.update(
            tracker_id=tracker.id,
            request=UpdateAgentTaskTrackerRequest(
                last_processed_event_id=unprocessed_events[-1].id,
                status_reason=f"Processed batch of {len(unprocessed_events)} events"
            )
        )
```

### Agent Task Tracker for Cursor Coordination

**Agent Task Tracker** provides cursor-based coordination for sophisticated event processing patterns:

```python
@acp.on_task_event_send
async def cursor_coordinated_processing(params: SendEventParams):
    # Agent Task Tracker acts as processing cursor
    tracker = await adk.agent_task_tracker.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    # Get unprocessed events since last cursor position
    unprocessed_events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id,
        last_processed_event_id=tracker.last_processed_event_id,
        limit=50
    )
    
    if not unprocessed_events:
        return  # No new events to process
    
    # Process events AND get conversation context from TaskMessages
    conversation_messages = await adk.messages.list(task_id=params.task.id)
    
    # Process with full context from both events and messages
    for event in unprocessed_events:
        await process_with_full_context(event, conversation_messages)
    
    # Update cursor - forward-only movement after successful processing
    await adk.agent_task_tracker.update(
        tracker_id=tracker.id,
        request=UpdateAgentTaskTrackerRequest(
            last_processed_event_id=unprocessed_events[-1].id,
            status_reason=f"Processed {len(unprocessed_events)} events with conversation context"
        )
    )
```

**Key Benefits:**

- **Resumable Processing**: Pick up where you left off after restarts
- **Forward-Only Progress**: Cursors prevent duplicate processing
- **Batch Coordination**: Process multiple events atomically
- **Progress Tracking**: Track processing status across instances

!!! warning "Cursor Rules"
    - Cursors can only move **forward** - never backward
    - Update cursor **ONLY** after processing is complete
    - Use Agent Task Tracker cursors for **coordination** - they're optional for basic processing

### Database Write Order Guarantees

**Critical**: Events are written to the database **BEFORE** being sent to the agent:

1. **User sends message** → TaskMessage created in messages table
2. **Event created** → Event written to events table  
3. **Event delivered** → Agent receives event via ACP
4. **Agent processes** → Can query both events and messages tables

This ensures agents can always access the event data, even if there are delivery failures.

## Key Takeaway

!!! info "Remember the Architecture"
    - **Events**: Persistent processing coordination stored in events table (written BEFORE ACP delivery)
    - **TaskMessages**: Persistent user conversation stored in messages table  
    - **Use events for processing coordination**, **TaskMessages for conversation context**
    - **Both are queryable and persistent** - they serve different purposes 