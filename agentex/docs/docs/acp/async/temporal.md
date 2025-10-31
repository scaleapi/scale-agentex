# Temporal Async ACP

**Temporal Async ACP** provides production-ready agent development with **durable execution**, **fault tolerance**, and **automatic state management**. Instead of implementing ACP handlers directly, you implement Temporal workflows that are automatically integrated with the ACP protocol.

## When to Use

### Perfect For:

✅ **Production Applications**

- Enterprise-grade reliability requirements
- Business-critical workflows
- High-availability systems

✅ **Long-Running Processes**

- Workflows spanning hours, days, or weeks
- Complex orchestration with multiple steps
- Processes requiring automatic retries

✅ **Large-Scale Systems**

- Millions of concurrent workflows
- High-throughput processing
- Horizontal scalability needs

### Not Ideal For:

❌ **Learning Agentex basics** - Start with Base Async ACP
❌ **Simple prototypes** - Higher complexity overhead
❌ **Development without Temporal** - Requires Temporal infrastructure

## Key Differences from Base Async ACP

### No Manual ACP Handlers

The `TemporalACP` class automatically implements the three ACP handlers:

- `@acp.on_task_create` → Forwards to your `@workflow.run` method
- `@acp.on_task_event_send` → Forwards to your `@workflow.signal` method
- `@acp.on_task_cancel` → Handled automatically by Temporal

### Temporal Workflow Implementation

Instead of ACP handlers, you implement standard Temporal workflows:

**workflow.py**
```python
from temporalio import workflow
from agentex import adk
from agentex.lib.types.acp import CreateTaskParams, SendEventParams
from agentex.core.temporal.workflows.workflow import BaseWorkflow
from agentex.core.temporal.types.workflow import SignalName
from agentex.types.message_author import MessageAuthor
from agentex.types.text_content import TextContent

@workflow.defn(name="my-agent-workflow")
class MyAgentWorkflow(BaseWorkflow):
    def __init__(self):
        super().__init__(display_name="My Agent")
        self._complete_task = False

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> str:
        """Handles task creation - equivalent to @acp.on_task_create"""

        # Send initial message
        await adk.messages.create(
            task_id=params.task.id,
            content=TextContent(
                author=MessageAuthor.AGENT,
                content=f"Hello! Task created with params: {params.params}"
            ),
        )

        # Wait for task completion
        await workflow.wait_condition(
            lambda: self._complete_task,
            timeout=None
        )
        return "Task completed"

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        """Handles events - equivalent to @acp.on_task_event_send"""

        # Echo user message
        await adk.messages.create(
            task_id=params.task.id,
            content=params.event.content
        )

        # Send agent response
        await adk.messages.create(
            task_id=params.task.id,
            content=TextContent(
                author=MessageAuthor.AGENT,
                content="I received your message!"
            ),
        )
```

### Automatic ACP Integration

**acp.py**
```python
import os
from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.fastacp import TemporalACPConfig

# Create the ACP server
acp = FastACP.create(
    acp_type="async",
    config=TemporalACPConfig(
        type="temporal",
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    )
)

# No handlers to register - automatically handled by TemporalACP
# @acp.on_task_create → handled by @workflow.run
# @acp.on_task_event_send → handled by @workflow.signal(name=SignalName.RECEIVE_EVENT)
# @acp.on_task_cancel → handled automatically by Temporal
```

## State Management

### Two Options for State

Temporal ACP offers flexible state management - use Temporal's built-in event sourcing for small state, or Agentex's state storage for larger data.

| Data Consideration | Temporal Workflow State | Agentex State |
|-------------------|-------------------------|---------------|
| **Data size limit** | ⚠️ Up to 2MB per message | ✅ Up to 16MB (blob storage planned) |
| **Small variables** | ✅ Turn counters, flags | ❌ Overkill for small data |
| **Large datasets** | ❌ Size limitations | ✅ Handles larger data volumes |
| **Automatic persistence** | ✅ Built-in with event history | ⚠️ Manual CRUD operations |
| **Cross-agent sharing** | ❌ Workflow-specific | ✅ Task-scoped access |
| **Performance** | ✅ Fast in-memory access | ⚠️ Network calls required |

### Temporal Workflow State (Small Data)

```python
from agentex.utils.model_utils import BaseModel

class StateModel(BaseModel):
    input_list: List[Dict]  # OpenAI chat format
    turn_number: int

@workflow.defn(name="chat-agent-workflow")
class ChatAgentWorkflow(BaseWorkflow):
    def __init__(self):
        super().__init__(display_name="Chat Agent")
        self._complete_task = False
        self._state = None  # Initialized in on_task_create

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> str:
        # Initialize workflow state - stored in Temporal's event history
        self._state = StateModel(
            input_list=[],
            turn_number=0,
        )

        await workflow.wait_condition(lambda: self._complete_task)
        return "Task completed"

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        # Update workflow state directly
        self._state.turn_number += 1
        self._state.input_list.append({
            "role": "user",
            "content": params.event.content.content
        })

        # Use state for LLM calls
        run_result = await adk.providers.openai.run_agent_streamed_auto_send(
            task_id=params.task.id,
            input_list=self._state.input_list,
            agent_name="Assistant",
            agent_instructions="You are a helpful assistant."
        )

        self._state.input_list = run_result.final_input_list
```

### Agentex State Storage (Large Data)

```python
from agentex.utils.model_utils import BaseModel

class ExtensiveConversationState(BaseModel):
    full_conversation_history: list[dict] = []  # Thousands of messages
    user_profile: dict = {}
    conversation_summaries: list[str] = []

@workflow.defn(name="extensive-chat-workflow")
class ExtensiveChatWorkflow(BaseWorkflow):
    def __init__(self):
        super().__init__(display_name="Extensive Chat")
        self._complete_task = False
        self._recent_messages = []  # Lightweight workflow state
        self._turn_count = 0

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> str:
        # Initialize Agentex state for extensive data (up to 16MB)
        initial_state = ExtensiveConversationState(
            full_conversation_history=[],
            user_profile={},
            session_metadata={"created_at": workflow.now().isoformat()}
        )

        await adk.state.create(
            task_id=params.task.id,
            agent_id=params.agent.id,
            state=initial_state.model_dump()
        )

        await workflow.wait_condition(lambda: self._complete_task)
        return "Task completed"

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        # Update lightweight workflow state
        self._turn_count += 1
        user_message = {"role": "user", "content": params.event.content.content}
        self._recent_messages.append(user_message)

        # Keep only last 10 in workflow state (under 2MB limit)
        if len(self._recent_messages) > 10:
            self._recent_messages = self._recent_messages[-10:]

        # Get extensive state when needed
        state_record = await adk.state.get_by_task_and_agent(
            task_id=params.task.id,
            agent_id=params.agent.id
        )

        if state_record:
            conversation_state = ExtensiveConversationState.model_validate(state_record.state)
        else:
            conversation_state = ExtensiveConversationState()

        # Store complete history in Agentex state (handles up to 16MB)
        conversation_state.full_conversation_history.append({
            **user_message,
            "timestamp": workflow.now().isoformat(),
            "turn": self._turn_count
        })

        # Use recent messages for LLM (fast) while preserving full history
        run_result = await adk.providers.openai.run_agent_streamed_auto_send(
            task_id=params.task.id,
            input_list=self._recent_messages,
            agent_name="Memory-Enhanced Assistant",
            agent_instructions=f"User has sent {len(conversation_state.full_conversation_history)} messages."
        )

        # Update both states
        self._recent_messages = run_result.final_input_list
        agent_response = run_result.final_input_list[-1]

        conversation_state.full_conversation_history.append({
            **agent_response,
            "timestamp": workflow.now().isoformat(),
            "turn": self._turn_count
        })

        # Persist extensive state
        await adk.state.update(
            state_id=state_record.id if state_record else None,
            task_id=params.task.id,
            agent_id=params.agent.id,
            state=conversation_state.model_dump()
        )
```

## Worker Configuration

**run_worker.py**
```python
import asyncio
from agentex.core.temporal.activities import get_all_activities
from agentex.core.temporal.workers.worker import AgentexWorker
from agentex.environment_variables import EnvironmentVariables
from workflow import MyAgentWorkflow

environment_variables = EnvironmentVariables.refresh()

async def main():
    task_queue_name = environment_variables.WORKFLOW_TASK_QUEUE
    if task_queue_name is None:
        raise ValueError("WORKFLOW_TASK_QUEUE is not set")

    worker = AgentexWorker(task_queue=task_queue_name)

    # get_all_activities() returns all temporal activities required for ADK
    await worker.run(
        activities=get_all_activities(),
        workflow=MyAgentWorkflow,
    )

if __name__ == "__main__":
    asyncio.run(main())
```

## Advantages

- **Automatic Durability** - Workflow state persisted automatically
- **Event History** - Maintained for replay and debugging
- **Fault Tolerance** - Built-in with automatic retries
- **Scalability** - Millions of concurrent workflows supported
- **Observability** - Built-in monitoring via Temporal Web UI
- **Versioning** - Safe workflow updates
- **Production Features** - Testing frameworks, multi-region deployment

---

## Next Steps

- **Getting started?** Learn about [Base Async ACP](base.md) first
- **Need to migrate?** Check the [Migration Guide](../../concepts/migration_guide.md)
- **New to Agentex?** Follow the [Quick Start Guide on GitHub](https://github.com/scaleapi/scale-agentex#quick-start)
- **Ready to build?** Check out [Temporal Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/100_temporal)
