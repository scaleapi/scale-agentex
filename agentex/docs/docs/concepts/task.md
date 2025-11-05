# Task Concepts

Tasks are the central entity in Agentex, representing a conversation or workflow instance between a client and an agent. Understanding tasks is fundamental to building effective agents.

## What is a Task?

A **Task** represents a stateful conversation or workflow session. It's the top-level container that holds:

- Messages exchanged between client and agent
- Persistent state managed by the agent  
- Lifecycle information (creation, status, completion)
- Metadata about the conversation

Think of a task like a chat session, customer support ticket, or workflow execution that can span multiple interactions over time.

## Task Relationships

!!! info "For Detailed Implementation"
    This section explains the architectural relationships between core Agentex entities. For specific implementation patterns, refer to the [Agent Client Protocol guides](../acp/overview.md).

### Task ↔ Messages (One-to-Many)

**Tasks maintain a flat ledger of messages.** This flat design is an intentional architectural decision that enables flexible multi-actor communication patterns.

#### Why This Design?

```python
# A single task's message ledger might include:
messages = [
    {"author": "USER", "content": "I need help with analysis"},           # Human user
    {"author": "AGENT", "content": "I'll analyze this for you"},          # Primary agent
    {"author": "AGENT", "content": "Analysis complete: ..."},             # Primary agent result
    {"author": "USER", "content": "Can you also check the data?"},        # Human user follow-up
    {"author": "AGENT", "content": "Data validation in progress..."},     # Secondary agent (if multi-agent)
    {"author": "AGENT", "content": "Data is valid"},                      # Secondary agent result
]
```

This flat structure allows:

- **Multi-agent systems** where different agents contribute to the same conversation
- **Complex user interactions** where multiple users (or user systems) participate
- **Simple message retrieval** without needing to understand actor hierarchies
- **Chronological ordering** that preserves the natural flow of communication

### Task ↔ Events (One-to-Many)

**Events are not persisted objects - they are notifications that wrap task message content.** When a new message arrives in the task message ledger, an event is generated to notify agents, but you should always operate on the actual TaskMessages.

#### Key Characteristics:

- **Notification System**: Events signal that new messages have arrived, like "new mail in your mailbox"
- **Content Wrapper**: Events contain `TaskMessageContent` but are not the source of truth
- **Ephemeral**: Events are notifications, not stored entities you query later
- **Triggering Mechanism**: In Async Agents, events trigger your `@acp.on_task_event_send` handlers

#### Processing Strategies:

You have two approaches when handling events:

1. **Process Event Content Directly**: Handle the `TaskMessageContent` wrapped in the event
2. **Process All New Messages**: Use the event as a trigger to fetch all new messages since your last cursor

```python
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Approach 1: Process the event's message content directly
    if params.event.content:
        user_message = params.event.content.content
        await process_single_message(user_message)
    
    # Approach 2: Treat event as "you have new mail" notification
    # Fetch all new messages since last processed
    all_messages = await adk.messages.list(task_id=params.task.id)
    new_messages = get_unprocessed_messages(all_messages, last_cursor)
```

### Using Agent Task Tracker for Coordinated Processing

For **Approach 2**, you can use **Agent Task Tracker** as a cursor system to track which events have been processed:

```python
@acp.on_task_event_send
async def handle_event_send_with_cursor(params: SendEventParams):
    # Get current processing cursor from Agent Task Tracker
    tracker = await adk.agent_task_tracker.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    # Get all unprocessed events since last cursor
    unprocessed_events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id,
        last_processed_event_id=tracker.last_processed_event_id,
        limit=50
    )
    
    if not unprocessed_events:
        return  # No new events to process
    
    # Process batch of events
    for event in unprocessed_events:
        # Process each event and corresponding task messages
        if event.content:
            await process_event_content(event.content)
    
    # Update cursor ONLY after all processing is complete
    await adk.agent_task_tracker.update(
        tracker_id=tracker.id,
        request=UpdateAgentTaskTrackerRequest(
            last_processed_event_id=unprocessed_events[-1].id,
            status_reason=f"Processed {len(unprocessed_events)} events"
        )
    )
```

**Benefits of cursor-based processing:**

- **Resumable**: Pick up where you left off after restarts
- **Batch Processing**: Process multiple events together efficiently  
- **Progress Tracking**: Know exactly which events have been handled
- **Race Reduction**: Coordinate processing across instances

!!! info "Optional Coordination"
    Agent Task Tracker cursors are **optional** - only use them when you need sophisticated processing coordination patterns. For simple event handling, processing events individually works fine.

!!! warning "Cursor Safety"
    Cursors can only move **forward** - never backward. Only update `last_processed_event_id` after processing is completely finished.

### Task ↔ State (One-to-One per Agent)

**State is scoped to the union of a task and an agent.** Each agent maintains its own isolated state when working on a specific task.

#### Key Characteristics:

- **Agent-Scoped State**: Each `(task_id, agent_id)` pair gets its own state
- **Isolation**: Agents don't interfere with each other's state, even on the same task
- **Simplicity**: Individual agents only need to manage their own state
- **Parallel Safety**: Multiple agents can work on the same task without state conflicts

#### Why This Design?

```python
# Task "task_123" with multiple agents:

# Agent A's state (focused on analysis)
agent_a_state = {
    "analysis_stage": "data_processing",
    "processed_rows": 1500,
    "findings": ["anomaly_1", "pattern_2"]
}

# Agent B's state (focused on reporting) 
agent_b_state = {
    "report_format": "executive_summary",
    "sections_completed": ["intro", "methodology"],
    "pending_charts": ["trend_analysis", "comparison"]
}

# Agent C's state (focused on validation)
agent_c_state = {
    "validation_rules": ["rule_1", "rule_2", "rule_3"],
    "validated_items": 45,
    "errors_found": []
}
```

This design enables:

- **Simple reasoning**: Each agent only considers its own state and responsibilities
- **Parallel execution**: Multiple agents work simultaneously without coordination overhead
- **Code maintainability**: Agent logic remains focused and doesn't need to understand other agents
- **System reliability**: One agent's state issues don't affect other agents

## Task Handling by Agent Type

The way you work with tasks depends heavily on which agent type you choose. Agentex supports three agent types: [Sync Agents](../agent_types/sync.md), [Async Agents (Base)](../agent_types/async/base.md), and [Async Agents (Temporal)](../agent_types/async/temporal.md).

!!! info "Choosing Your Agent Type"
    Not sure which agent type is right for you? See the [Choose Your Agent Type](../getting_started/choose_your_agent_type.md) guide for a detailed comparison and decision matrix.

### Sync Agents - Simple Request-Response

**Sync Agents** treat tasks as lightweight conversation containers where the Agentex service handles all task and message lifecycle management automatically.

**What Agentex Handles (Automatic):**

- Creates or retrieves tasks (auto-created for single-turn interactions, or reused if you pass a `task_id` for multi-turn conversations)
- Saves all incoming messages to conversation history
- Routes requests to your handler
- Persists all your response messages to conversation history
- Returns responses to clients

**What You Implement (Your Code):**

- Process the incoming message from the `TaskMessageContent` payload.
- Return or yield your agent's response (return for blocking responses, yield for streaming)

**Why This Works:**

Because Agentex persists both the inputs and outputs, you can focus entirely on business logic - just transform inputs into outputs. No need to manage tasks, save messages, or handle lifecycle. You write pure processing code: receive message → generate response → return or yield.

**Key Characteristics:**

- One handler: `@acp.on_message_send`
- Tasks and messages managed automatically
- Stateless by default (though you can add state via `adk.state` API)
- Blocking, synchronous execution

**Task Interaction Pattern:**
```python
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    """Only handler needed for Sync Agents"""
    
    task = params.task          # Task context provided automatically
    user_message = params.content.content
    
    # Process the message and return response
    response = await process_user_message(user_message)
    
    return TextContent(
        author=MessageAuthor.AGENT,
        content=response
    )
```

**Lifecycle Overview:**
```python
# 1. Task Creation - Handled automatically by Agentex

# 2. Message Processing - Your responsibility
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    pass

# 3. Task Completion - Unnecessary in Sync Agents
```

### Async Agents - Full Lifecycle Management

**Async Agents** (both Base and Temporal) give you complete control over task lifecycle with event-driven handlers. Unlike Sync Agents, you explicitly manage when tasks start, how they process events, and when they clean up.

**What Agentex Handles (Automatic):**

- Routes lifecycle events to your three handlers (`on_task_create`, `on_task_event_send`, `on_task_cancel`)
- Delivers events asynchronously (events are notifications, not persisted messages - you decide what to persist)
- Returns responses to clients

**What You Implement (Your Code):**

- Initialize tasks in `@acp.on_task_create` (send welcome messages, set up state)
- Process events in `@acp.on_task_event_send` (handle user messages, business logic)
- Clean up in `@acp.on_task_cancel` (archive data, release resources)
- Explicitly persist ALL messages using `adk.messages.create()` - including incoming user messages (this gives you control to preprocess or filter ephemeral events like webhooks before saving them)
- Manage your own state using `adk.state` API (Base) or workflow variables (Temporal)

**Why This Works:**

You have full control over the task lifecycle, allowing complex workflows like multi-step processes, conditional logic, and long-running operations. The trade-off is you must explicitly manage message creation and state - Agentex provides the infrastructure but you orchestrate the flow.

**Lifecycle Overview:**
```python
# 1. Task Creation - Initialize whatever you need
@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    # Set up initial state, send welcome messages
    pass

# 2. Task Processing - Handle ongoing interactions
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Handle user messages, business logic, update state, send responses
    pass

# 3. Task Completion - Clean up and archive
@acp.on_task_cancel
async def handle_task_cancel(params: CancelTaskParams):
    # Archive data, release resources
    pass
```

!!! note "Base vs Temporal: State Persistence"
    **With Temporal:** Your workflow state (class variables) persists automatically across restarts and failures. No manual state management needed.
    
    **With Base:** You must manually persist state using the `adk.state` API.
    
    Learn more in the [Temporal Development Overview](../temporal_development/overview.md).


