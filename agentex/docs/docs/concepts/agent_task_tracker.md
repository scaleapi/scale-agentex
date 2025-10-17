# Agent Task Tracker

Agent Task Trackers are **optional** coordination objects that help track processing progress and status for agents working on tasks. They are useful for building resumable and stateful processing patterns, but are not required for basic agent functionality.

## What Are Agent Task Trackers?

Agent Task Trackers are **optional processing coordination records** that track the state of agent work on specific tasks. Each tracker represents the relationship between one agent and one task.

**Key Characteristics:**

- **Optional**: Not required for basic agent functionality
- **Automatically Created**: Generated when a task is assigned to an agent
- **Unique per Agent/Task**: One tracker per agent-task combination
- **Status Management**: Tracks processing state for coordination
- **Cursor-Based Progress**: Records processing position using `last_processed_event_id` as a cursor

## Agent Task Tracker Structure

```python
class AgentTaskTracker:
    id: str                          # Unique tracker identifier
    agent_id: str                    # Associated agent
    task_id: str                     # Associated task
    status: Optional[str]            # Processing status
    status_reason: Optional[str]     # Description of current status
    last_processed_event_id: Optional[str]  # CURSOR - tracks processing position
    created_at: datetime             # When tracker was created
    updated_at: Optional[datetime]   # Last update timestamp
```

## When to Use Agent Task Trackers

Use Agent Task Trackers when you need:

- **Batch Processing**: Wait for multiple events before processing together
- **State-Based Processing**: Ignore events when agent is busy, process accumulated events when ready
- **Resumable Processing**: Resume from specific event positions after restarts
- **Long Workflows**: Coordinate multi-phase processing (e.g., research → analysis → response)

!!! warning "Optional Feature"
    Agent Task Trackers are **not required** for basic agent functionality. Only use them when you need stateful processing coordination.

## Cursor Behavior (Critical)

The `last_processed_event_id` field acts as a **CURSOR** with strict rules:

!!! danger "Cursor Rules"
    1. **Forward-Only**: Cursors can only move forward - never backward
    2. **Set After Completion**: Only update cursor AFTER processing is finished
    3. **Update Fails on Rollback**: Attempting to set cursor to an earlier event will fail

## Common Processing Patterns

### Simple Batch Processing
Wait for multiple events, then process together:
```python
@acp.on_task_event_send
async def batch_handler(params: SendEventParams):
    unprocessed_events = await get_unprocessed_events(params.task.id, params.agent.id)
    
    if len(unprocessed_events) >= 5:  # Wait for batch of 5
        await process_batch(unprocessed_events)
        await commit_cursor(unprocessed_events[-1].id)
```

### State-Based Processing
Ignore events when not ready, process when ready:
```python
@acp.on_task_event_send
async def state_handler(params: SendEventParams):
    if agent_busy():
        return  # Events accumulate while agent works
    
    # Agent ready - get accumulated events and decide strategy
    events = await get_unprocessed_events(params.task.id, params.agent.id)
    await start_processing_workflow(events)
```

!!! tip "Lightweight Handlers"
    Keep event handlers fast - they should check conditions and kick off background processing, not do heavy work directly.

## Basic Usage Pattern

```python
async def process_with_tracker(task_id: str, agent_id: str):
    # Get current tracker state
    tracker = await adk.agent_task_tracker.get_by_task_and_agent(
        task_id=task_id,
        agent_id=agent_id
    )
    
    # Get unprocessed events since last cursor
    events = await adk.events.list_events(
        task_id=task_id,
        agent_id=agent_id,
        last_processed_event_id=tracker.last_processed_event_id,
        limit=50
    )
    
    if not events:
        return  # No new events to process
    
    # Process all events in the batch
    for event in events:
        await process_event(event)
    
    # Update cursor ONLY after all processing is complete
    await adk.agent_task_tracker.update(
        tracker_id=tracker.id,
        request=UpdateAgentTaskTrackerRequest(
            last_processed_event_id=events[-1].id,
            status_reason=f"Processed {len(events)} events"
        )
    )
```

## Querying Agent Task Trackers

```python
# Get by tracker ID
tracker = await adk.agent_task_tracker.get(tracker_id="tracker_123")

# Get by agent and task (most common pattern)
tracker = await adk.agent_task_tracker.get_by_task_and_agent(
    agent_id="agent_456",
    task_id="task_789"
)
```

## Key Points

- **Optional Feature**: Agent Task Trackers are not required for basic functionality
- **Cursor-Only Updates**: Only update `last_processed_event_id` after processing completion
- **Forward Movement**: Cursors cannot move backward - updates that try to rollback will fail
- **Event Accumulation**: Events naturally accumulate when agents ignore them during busy periods
- **Lightweight Handlers**: Event handlers should be fast - heavy processing happens asynchronously

## Next Steps

- Learn about [Events](events.md) for understanding the processing coordination relationship
- Explore [State Management](state.md) for maintaining agent context across processing
- See [Critical Concepts - Events vs Messages](callouts/events_vs_messages.md) for critical architectural distinctions
- Review the [Tutorials](../tutorials.md) for hands-on coordination examples 