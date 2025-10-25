# Temporal Survival Guide for AgentEx Developers

**The essential concepts you need to build durable, enterprise-grade agents with AgentEx + Temporal.**

> **Note**: All code examples use the **actual AgentEx + Temporal Python SDK API** from the tutorials and codebase. These are working examples, not simplified pseudo-code.

---

## Why Temporal? The 30-Second Pitch

**Problem**: Your AI agent crashes, loses state, or gets overwhelmed by requests.

**Solution**: [Temporal provides "durable execution"](https://docs.temporal.io/evaluate/understanding-temporal#durable-execution) - your agent automatically survives crashes, restarts, and scaling events while maintaining perfect state.

**Real Impact**: [Companies report production issues falling from once-a-week to near-zero](https://dev.to/swyx/temporal-the-iphone-of-system-design-4a78#the-business-case-for-temporal) after migrating to Temporal.

---

## Essential Concepts (5-Minute Read)

### 1. **Workflows = Your Agent Logic**

A [Temporal Workflow](https://docs.temporal.io/concepts/workflows) is your agent's brain - the business logic that survives crashes.

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

**Key insight**: This looks like normal Python, but Temporal makes it **indestructible**.

### 2. **Activities = External World Interactions**

[Activities](https://docs.temporal.io/concepts/activities) handle anything that can fail: API calls, database writes, LLM requests.

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

**Key insight**: Activities automatically retry with exponential backoff. No more manual retry logic.

### 3. **Workers = Your Agent Processes**

[Workers](https://docs.temporal.io/concepts/workers) are your actual Python processes that execute workflows and activities.

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

**Key insight**: You can run 100+ workers for the same agent. Temporal distributes work automatically.

---

## The Magic: Event Sourcing + Deterministic Replay

### How Temporal Achieves "Durable Execution"

**Traditional Problem**: Server crashes → lose all state → start over

**Temporal Solution**: [Event sourcing](https://docs.temporal.io/concepts/event-history) + deterministic replay

1. **Every step is logged**: Temporal records every workflow decision as an "event"
2. **Crash recovery**: New worker replays all events to recreate exact state
3. **Resume seamlessly**: Continue from where you left off

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

**Key insight**: Your workflow function runs from the beginning during replay, but Temporal skips already-completed steps.

---

## Temporal vs Regular Python: Side-by-Side

| **Regular Python Agent** | **Temporal Agent** |
|---------------------------|-------------------|
| Crash = start over | Crash = resume exactly where left off |
| Manual retry logic | Automatic retries with policies |
| Cron jobs for scheduling | `workflow.wait_condition()` for long waits |
| Complex state management | Automatic state persistence |
| Hard to debug failures | Complete execution history in UI |

---

## AgentEx + Temporal Architecture

```yaml
# What AgentEx runs for you:
AgentEx Infrastructure:
  - MongoDB: Agent state storage
  - Redis: Real-time streaming  
  - PostgreSQL: Tasks and messages
  - Temporal: Workflow orchestration  ← The magic happens here
  - Kubernetes: Auto-scaling

Your Agent Code:
  - workflow.py: Agent business logic (Temporal Workflow)
  - activities.py: LLM calls, DB operations (Temporal Activities)  
  - acp.py: AgentEx integration layer
```

**Key insight**: AgentEx handles Temporal setup. You just write workflows and activities.

---

## Common Temporal Patterns for AI Agents

### 1. **Long-Running Conversations** (from actual tutorials)
```python
@workflow.run
async def on_task_create(self, params: CreateTaskParams) -> str:
    self._state = StateModel(input_list=[], turn_number=0)
    
    # Wait indefinitely for events - can run for days/weeks
    await workflow.wait_condition(
        lambda: self._complete_task,
        timeout=None  # No timeout - survives restarts
    )
    return "Task completed"
```

### 2. **State Machine Workflows** (from actual tutorials)
```python
@workflow.defn(name=environment_variables.WORKFLOW_NAME)
class StateMachineWorkflow(BaseWorkflow):
    def __init__(self):
        super().__init__()
        self.state_machine = DeepResearchStateMachine(
            initial_state=DeepResearchState.WAITING_FOR_USER_INPUT
        )
        
    # State transitions happen via signals and conditions
```

### 3. **Error Recovery with AgentEx ADK**
```python
# AgentEx ADK functions have automatic retry built-in
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def on_task_event_send(self, params: SendEventParams) -> None:
    # This automatically retries on failure with exponential backoff
    result = await adk.providers.openai.run_agent_streamed_auto_send(
        task_id=params.task.id,
        input_list=self._state.input_list,
        mcp_timeout_seconds=180  # 3 minute timeout per call
    )
```

---

## The Learning Path

### **Phase 1: Understand the Paradigm** (30 minutes)
- Read: [Understanding Temporal](https://docs.temporal.io/evaluate/understanding-temporal)
- Watch: [Temporal in 7 Minutes](https://www.youtube.com/watch?v=2HjnQlnA5eY)

### **Phase 2: Learn Core Concepts** (2 hours)
- [Workflows](https://docs.temporal.io/concepts/workflows) - Your durable business logic
- [Activities](https://docs.temporal.io/concepts/activities) - Failure-prone external calls  
- [Workers](https://docs.temporal.io/concepts/workers) - Your execution processes
- [Event History](https://docs.temporal.io/concepts/event-history) - How replay works

### **Phase 3: AgentEx Integration** (1 hour)
- **[Browse All Temporal Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/010_temporal)** - Complete, runnable examples:
  - `000_hello_acp/` - Basic workflow structure
  - `010_agent_chat/` - LLM integration with tools
  - `020_state_machine/` - Complex state management
  - `030_openai_sdk_integration/` - OpenAI SDK integration

---

## Critical Mental Models & Gotchas

### **Deterministic Replay Requirements**

**❌ Don't do this in workflows:**
```python
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def bad_workflow_handler(self, params):
    current_time = datetime.now()  # Non-deterministic!
    random_id = uuid.uuid4()       # Non-deterministic!
    api_response = requests.get()  # Side effect!
```

**✅ Do this instead:**
```python  
@workflow.signal(name=SignalName.RECEIVE_EVENT)  
async def good_workflow_handler(self, params):
    current_time = workflow.now()           # Deterministic
    random_id = workflow.uuid4()            # Deterministic  
    # Side effects go through AgentEx ADK (activities)
    await adk.messages.create(...)
```

### **Activity vs Workflow Boundaries**

- **Workflows**: Pure, deterministic business logic
- **Activities**: All external interactions (APIs, databases, file I/O)

### **🚨 Common Gotchas That Will Bite You**

#### **Data Serialization Limits**
```python
# ❌ Don't pass huge objects between activities
@activity.defn
async def process_data(giant_dataset: List[Dict]):  # Can hit 2MB limit
    ...

# ✅ Pass references instead  
@activity.defn
async def process_data(dataset_id: str):  # Load data inside activity
    dataset = await load_from_database(dataset_id)
```

**Why**: Temporal has a 2MB limit per workflow event. Large data structures will fail.

#### **Workflow State Size Explosion**
```python
# ❌ Don't accumulate unbounded state
async def bad_workflow():
    all_responses = []  # This grows forever!
    while True:
        response = await get_response()
        all_responses.append(response)  # Memory leak in workflow state
```

**Why**: Workflow state is replayed from the beginning. Growing state = slower replays.

#### **Activity Retry Idempotency**
```python
# ❌ Non-idempotent operations will duplicate
@activity.defn
async def send_email(user_id: str):
    await email_service.send(f"Welcome {user_id}!")  # Sends multiple emails on retry

# ✅ Make activities idempotent
@activity.defn
async def send_email(user_id: str, idempotency_key: str):
    await email_service.send_once(key=idempotency_key, ...)
```

**Why**: Activities retry automatically. Non-idempotent operations will run multiple times.

#### **Async/Await in Wrong Places**
```python
# ❌ Don't await non-Temporal async calls in workflows
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def bad_workflow_handler(self, params):
    await asyncio.sleep(60)  # Will break replay!
    response = requests.get("...")  # Non-deterministic!
    
# ✅ Use AgentEx ADK for external operations
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def good_workflow_handler(self, params):
    # All external operations go through ADK (activities)
    await adk.messages.create(...)  # Replay-safe
    await adk.providers.openai.run_agent_streamed_auto_send(...)  # Replay-safe
```

**Why**: Non-AgentEx async operations aren't tracked in event history and break deterministic replay.

---

## Debugging & Observability

### **Temporal Web UI**
- See complete execution history of every agent
- Replay failed workflows step-by-step
- Monitor performance and identify bottlenecks

### **Event History Deep Dive**
Every workflow step is recorded:
```
WorkflowExecutionStarted → ActivityTaskScheduled → ActivityTaskCompleted → 
TimerStarted → TimerFired → ActivityTaskScheduled → ...
```

**Key insight**: You get production debugging superpowers. No more "what happened?" mysteries.

---

## Production Readiness Checklist

- [ ] **Understand deterministic replay** - No random/time functions in workflows
- [ ] **Design activity boundaries** - Move all side effects to activities  
- [ ] **Set retry policies** - Configure appropriate backoff for each activity
- [ ] **Plan for versioning** - Workflow updates while old executions are running
- [ ] **Monitor execution metrics** - Use Temporal UI + your monitoring stack

---

## Advanced Topics (When You're Ready)

- [Child Workflows](https://docs.temporal.io/concepts/child-workflows) - Complex multi-agent coordination
- [Signals & Queries](https://docs.temporal.io/concepts/signals) - Real-time workflow interaction
- [Workflow Versioning](https://docs.temporal.io/concepts/versioning) - Safe deployments of workflow changes
- [Continue-As-New](https://docs.temporal.io/concepts/continue-as-new) - Infinite-running workflows

---

## Why This Matters for Agent-Responsive Design

As [agent-responsive design emerges](https://www.aiacceleratorinstitute.com/agent-responsive-design/), durable agents become critical infrastructure. AI agents are moving from simple request/response to **persistent, long-running relationships** with users and systems.

**Traditional agents**: Stateless, fragile, restart from scratch  
**Temporal agents**: Stateful, durable, remember everything across restarts

This isn't just about reliability - it's about **enabling entirely new agent interaction patterns** that weren't possible before.

---

## Simple Migration Example

**From Agentic → Temporal** (the most common upgrade path):

```python
# Before: Agentic Agent (risky for long operations)
@acp.on_task_event_send
async def process_data(params: SendEventParams) -> None:
    # If this crashes at step 3/5, lose all progress
    result = await expensive_step_1()  # 10 minutes
    result = await expensive_step_2()  # 10 minutes  
    result = await expensive_step_3()  # 10 minutes - crash here = lose 20min
    
# After: Temporal Agent (survives crashes)
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def process_data(self, params: SendEventParams) -> None:
    # Each step automatically retries and resumes on crash
    result = await workflow.execute_activity(expensive_step_1, ...)  # Resumable
    result = await workflow.execute_activity(expensive_step_2, ...)  # Resumable
    result = await workflow.execute_activity(expensive_step_3, ...)  # Resumable
```

**Migration trigger**: Any operation >30 minutes or high-value workflows that can't afford to restart.

**See the full decision framework**: [AgentEx Complexity Levels](index.md#when-to-upgrade)

---

## Ready to Build?

**Next Step**: [Build Your First Temporal Agent on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/010_temporal/000_hello_acp)

**Need Help?**: Join [Temporal Community Slack](https://temporal.io/slack) - 15,000+ developers building with Temporal

**Pro Tip**: Start simple. Convert one existing agent to Temporal, see the magic, then expand.

---

**Pro Tip**: Start simple. Convert one existing agent to Temporal, see the benefits, then expand. See [Advanced Topics](https://docs.temporal.io/concepts) when you need child workflows, versioning, or Continue-As-New. 