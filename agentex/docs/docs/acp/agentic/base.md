# Base Agentic ACP

**Base Agentic ACP** is the foundational implementation designed for learning and development environments. It provides complete control over task lifecycle while using Agentex's built-in state management.

## When to Use

### Perfect For:

✅ **Learning and Development**

- Understanding Agentic patterns
- Practicing state management concepts
- Learning multi-step workflow design

✅ **Development and Testing**

- Building proof-of-concept agents
- Testing workflow logic
- Developing without production constraints

✅ **Simple Workflows**

- Multi-step processes without enterprise durability needs
- Interactive applications with moderate state requirements

### Not Ideal For:

❌ **Production Critical Systems** - Use Temporal Agentic ACP
❌ **Very Large State Requirements** - Consider external storage
❌ **Enterprise Durability** - No advanced fault tolerance
❌ **High-Scale Operations** - Better suited for development

## State Management

Base Agentic ACP requires using Agentex's state management system:

```python
@acp.on_task_create
async def initialize_state(params: CreateTaskParams):
    """Create initial state structure"""

    initial_state = {
        "workflow_stage": "welcome",
        "user_data": {},
        "conversation_history": [],
        "metadata": {
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0"
        }
    }

    await adk.state.create(
        task_id=params.task.id,
        agent_id=params.agent.id,
        state=initial_state
    )

@acp.on_task_event_send
async def update_state(params: SendEventParams):
    """Update state during processing"""

    # Get current state
    state_record = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )

    if state_record:
        # Modify and save
        state_record.state["workflow_stage"] = "processing"
        state_record.state["last_updated"] = datetime.utcnow().isoformat()

        await adk.state.update(
            state_id=state_record.id,
            state=state_record.state
        )

@acp.on_task_cancel
async def cleanup_state(params: CancelTaskParams):
    """Clean up state on task completion"""

    state_record = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )

    if state_record:
        # Archive important data before cleanup
        await archive_final_state(params.task.id, state_record.state)
        await adk.state.delete(state_id=state_record.id)
```

## Multi-Step Workflow Pattern

```python
@acp.on_task_create
async def setup_multi_step_workflow(params: CreateTaskParams):
    """Initialize multi-step workflow"""

    workflow_steps = ["welcome", "collect_info", "verify", "complete"]

    initial_state = {
        "steps": workflow_steps,
        "current_step_index": 0,
        "step_data": {}
    }

    await adk.state.create(
        task_id=params.task.id,
        agent_id=params.agent.id,
        state=initial_state
    )

    await start_workflow_step(params.task.id, workflow_steps[0])

@acp.on_task_event_send
async def process_workflow_step(params: SendEventParams):
    """Process current workflow step"""

    state_record = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )

    if not state_record:
        return

    current_index = state_record.state["current_step_index"]
    steps = state_record.state["steps"]
    current_step = steps[current_index]

    # Process step
    step_result = await process_step(current_step, params.event.content)

    if step_result.completed:
        next_index = current_index + 1

        if next_index < len(steps):
            # Move to next step
            state_record.state["current_step_index"] = next_index
            state_record.state["step_data"][current_step] = step_result.data

            await adk.state.update(
                state_id=state_record.id,
                state=state_record.state
            )

            await start_workflow_step(params.task.id, steps[next_index])
        else:
            # Workflow complete
            await complete_workflow(params.task.id, state_record.state)
```

## Handler Parameters

### CreateTaskParams

Used in `@acp.on_task_create` for task initialization:

::: agentex.lib.types.acp.CreateTaskParams
    options:
      heading_level: 4
      show_root_heading: false
      show_source: false

### SendEventParams

Used in `@acp.on_task_event_send` for processing events:

::: agentex.lib.types.acp.SendEventParams
    options:
      heading_level: 4
      show_root_heading: false
      show_source: false

### CancelTaskParams

Used in `@acp.on_task_cancel` for cleanup:

::: agentex.lib.types.acp.CancelTaskParams
    options:
      heading_level: 4
      show_root_heading: false
      show_source: false

---

## Next Steps

- **Ready for production?** Learn about [Temporal Agentic ACP](temporal.md)
- **Need to upgrade?** See the [Migration Guide](../../concepts/migration_guide.md)
- **New to Agentex?** Follow the [Quick Start Guide on GitHub](https://github.com/scaleapi/scale-agentex#quick-start)
- **Ready to build?** Check out [Base Agentic Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/000_base)
