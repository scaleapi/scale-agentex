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

## When to Use Agent Task Trackers

Use Agent Task Trackers when you need:

- **Batch Processing**: Wait for multiple events before processing together
- **State-Based Processing**: Ignore events when agent is busy, process accumulated events when ready
- **Resumable Processing**: Resume from specific event positions after restarts
- **Long Workflows**: Coordinate multi-phase processing (e.g., research → analysis → response)

!!! info "Async ACP Only"
    Agent Task Trackers are only used in **Async ACP** agents. **Sync ACP** agents are automatically locked per request - each message is processed sequentially and blocking, so there's no need for manual cursor tracking. If you're using **Temporal workflows**, Temporal provides its own built-in mechanisms for state management, retries, and resumability, making Agent Task Trackers a bit redundant although you're free to use whatever mechanism of race condition handling you're comfortable with.

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
    # Get the current tracker to find last processed event
    tracker = await adk.agent_task_tracker.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    # Get unprocessed events since last cursor position
    unprocessed_events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id,
        last_processed_event_id=tracker.last_processed_event_id,
        limit=100
    )
    
    if len(unprocessed_events) >= 5:  # Wait for batch of 5
        # Process all events in the batch
        for event in unprocessed_events:
            response = await process_event(event)
            await adk.messages.create(
                task_id=params.task.id,
                content=response
            )
        
        # Update cursor after successful processing
        await adk.agent_task_tracker.update(
            tracker_id=tracker.id,
            request=UpdateAgentTaskTrackerRequest(
                last_processed_event_id=unprocessed_events[-1].id,
                status_reason=f"Processed batch of {len(unprocessed_events)} events"
            )
        )
```

### State-Based Processing

Ignore events when not ready, process when ready:

```python
@acp.on_task_event_send
async def state_handler(params: SendEventParams):
    # Check agent state - don't process if agent is busy
    state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    if state and state.state.get("processing_in_progress"):
        return  # Events accumulate while agent works
    
    # Agent ready - get accumulated events
    tracker = await adk.agent_task_tracker.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    events = await adk.events.list_events(
        task_id=params.task.id,
        agent_id=params.agent.id,
        last_processed_event_id=tracker.last_processed_event_id,
        limit=100
    )
    
    # Mark agent as busy and start processing
    await adk.state.update(
        state_id=state.id,
        task_id=params.task.id,
        agent_id=params.agent.id,
        state={"processing_in_progress": True}
    )
    
    # Process events and update cursor when done
    await process_events_workflow(events, params.task.id, params.agent.id, tracker.id)
```

