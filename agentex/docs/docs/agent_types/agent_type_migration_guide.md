# Migration Guide: Converting Between ACP Types

This guide provides comprehensive, step-by-step instructions for migrating agents between complexity levels as your requirements evolve. Each migration path includes real examples, common challenges, and testing strategies.

## Migration Paths Overview

| From | To | When to Migrate | Complexity Increase |
|------|----|-----------------|--------------------|
| **Sync** | **Async (Base)** | Need to change from a synchronous blocking agent to a session-based asynchronous agent. | Small |
| **Async (Base)** | **Async (Temporal)** | Need to build a long-running agent<br>• Handle complex multi-step / transactional tools<br>• Easier state management with just class variables<br>• Better race condition handling<br>• Better batch processing | Medium |

## Part 1: Sync ACP → Async (Base) ACP

Use `agentex init` to create a new project directory (select "Async (Base)" when prompted for ACP type), then migrate your code from the single `@acp.on_message_send` handler to the three Async (Base) handlers:

- `@acp.on_task_create` - Initialize state or send welcome messages
- `@acp.on_task_event_send` - Your main message processing logic (migrated from `on_message_send`)
- `@acp.on_task_cancel` - Cleanup when tasks end

**Key change:** You must manually create messages using `adk.messages.create()` instead of returning them.

### Before (Sync)

```python
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # Your logic here
    response = process_user_input(params.content.content)
    return TextContent(author=MessageAuthor.AGENT, content=response)
```

### After (Agentic Base)

```python
@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    # Optional: initialize state, send welcome message
    pass

@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Your logic here (migrated from on_message_send)
    response = process_user_input(params.event.content.content)

    # Manually create message (new requirement)
    await adk.messages.create(
        task_id=params.task.id,
        content=TextContent(author=MessageAuthor.AGENT, content=response)
    )

@acp.on_task_cancel
async def handle_task_cancel(params: CancelTaskParams):
    # Optional: cleanup resources
    pass
```

## Part 2: Async (Base) ACP → Async (Temporal) ACP

Use `agentex init` to create a new project directory (select "Async (Temporal)" when prompted for ACP type), then migrate your three handlers into a Temporal workflow:

- `@acp.on_task_create` → `@workflow.run` (workflow initialization)
- `@acp.on_task_event_send` → `@workflow.signal` (event processing)
- `@acp.on_task_cancel` → Handled automatically by Temporal

**Key changes:**
- State becomes class variables on the workflow
- Wrap API calls and side effects in Temporal activities for automatic retries
- Workflow state persists across server restarts

### Before (Agentic Base)

```python
@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    await adk.state.create(...)

@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Direct API calls
    result = await external_api.call(params.event.content)
    await adk.messages.create(task_id=params.task.id, content=result)

@acp.on_task_cancel
async def handle_task_cancel(params: CancelTaskParams):
    # Cleanup
    pass
```

### After (Agentic Temporal)

```python
@workflow.defn
class MyAgentWorkflow(BaseWorkflow):
    def __init__(self):
        super().__init__()
        self.state = {}  # State as class variables

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams):
        # Initialization logic
        self.state["initialized"] = True

        # Wait for events
        await workflow.wait_condition(lambda: self._complete_task)

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams):
        # Wrap API calls in activities (automatic retries)
        result = await workflow.execute_activity(
            external_api_activity,
            params.event.content,
            start_to_close_timeout=timedelta(minutes=5)
        )

        await workflow.execute_activity(
            create_message_activity,
            CreateMessageArgs(task_id=params.task.id, content=result),
            start_to_close_timeout=timedelta(seconds=30)
        )

# Define activities for side effects
@activity.defn
async def external_api_activity(content):
    return await external_api.call(content)

@activity.defn
async def create_message_activity(args):
    await adk.messages.create(task_id=args.task_id, content=args.content)
```

---

## Summary

Migration between ACP types follows clear patterns. Test your migrated agent with the same inputs to ensure equivalent behavior before deploying to production. 