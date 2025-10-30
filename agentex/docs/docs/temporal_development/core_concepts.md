# Core Concepts

## Essential Concepts

### 1. Workflows

A [Temporal Workflow](https://docs.temporal.io/concepts/workflows){target="_blank"} contains your agent's business logic with built-in crash resilience.

```python
# AgentEx Temporal Agent (actual API from codebase)
@workflow.defn(name="agent-workflow")
class ConversationWorkflow(BaseWorkflow):
    def __init__(self):
        super().__init__()
        self._complete_task = False

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> str:
        # Wait indefinitely for task completion
        await workflow.wait_condition(
            lambda: self._complete_task,
            timeout=None  # Can run for days/weeks
        )
        return "Task completed"

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        # Process each user message as it arrives
        await adk.messages.create(...)  # AgentEx activity
```

Workflows use standard Python syntax with Temporal durability guarantees.

### 2. Activities

[Activities](https://docs.temporal.io/concepts/activities){target="_blank"} handle operations that can fail: API calls, database writes, LLM requests.

```python
# AgentEx handles activities through the ADK
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def on_task_event_send(self, params: SendEventParams) -> None:
    # AgentEx ADK functions are automatically retried activities
    result = await adk.providers.openai.run_agent_streamed_auto_send(
        task_id=params.task.id,
        input_list=self._state.input_list  # Can fail, will retry
    )

    await adk.messages.create(
        task_id=params.task.id,
        content=TextContent(...)  # Can fail, will retry
    )
```

Activities automatically retry with exponential backoff.

### 3. Workers

[Workers](https://docs.temporal.io/concepts/workers){target="_blank"} are Python processes that execute workflows and activities.

```python
# AgentEx worker setup (from actual tutorials)
from agentex.core.temporal.workers.worker import AgentexWorker
from agentex.core.temporal.activities import get_all_activities

async def main():
    worker = AgentexWorker(task_queue="my-agent-queue")
    await worker.run(
        activities=get_all_activities(),  # AgentEx provides activities
        workflow=MyAgentWorkflow,
    )
```

Multiple workers can run for the same agent. Temporal distributes work automatically.

---

## Event Sourcing and Deterministic Replay

### How Temporal Achieves Durable Execution

Temporal uses [event sourcing](https://docs.temporal.io/concepts/event-history){target="_blank"} and deterministic replay to maintain workflow state:

1. **Event logging**: Temporal records every workflow decision as an event
2. **Crash recovery**: New workers replay all events to recreate exact state
3. **Seamless resumption**: Workflow continues from the point of interruption

```python
# What happens during replay:
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def on_task_event_send(self, params: SendEventParams) -> None:
    # Replay: "We already did this step" (skip)
    await adk.messages.create(...)

    # Replay: "We already did this step" (skip)
    result = await adk.providers.openai.run_agent_streamed_auto_send(...)

    # New: "This is where we crashed, continue from here"
    self._state.turn_number += 1  # ← Resumes here with updated state
```

Workflow functions run from the beginning during replay, but Temporal skips already-completed steps.

---

## Temporal vs Regular Python: Side-by-Side

| **Regular Python Agent** | **Temporal Agent** |
|---------------------------|-------------------|
| Crash = start over | Crash = resume exactly where left off |
| Manual retry logic | Automatic retries with policies |
| Cron jobs for scheduling | `workflow.wait_condition()` for long waits |
| Complex state management | Automatic state persistence |
| Hard to debug failures | Complete execution history in UI |
