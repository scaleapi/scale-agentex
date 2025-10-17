# State Management

Effective state management is crucial for building complex, stateful agents. This guide covers advanced patterns for managing agent and task state using the `adk.state` module.

## Overview

Agentex provides a powerful state management system that allows you to persist data across agent interactions. State is uniquely identified by the combination of `(task_id, agent_id)`, enabling multiple agents to work on the same task with isolated state.

## Basic State Operations

### Creating State

```python
from agentex import adk
from agentex.utils.model_utils import BaseModel

class ConversationState(BaseModel):
    messages: list[dict] = []
    user_preferences: dict = {}
    turn_count: int = 0

@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    # Initialize state when task is created
    initial_state = ConversationState(
        messages=[],
        user_preferences={},
        turn_count=0
    )
    
    await adk.state.create(
        task_id=params.task.id,
        agent_id=params.agent.id,
        state=initial_state,
        trace_id=params.task.id
    )
```

### Retrieving State

```python
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Get existing state
    task_state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id,
        trace_id=params.task.id
    )
    
    if task_state:
        # Convert to your state model
        state = ConversationState.model_validate(task_state.state)
    else:
        # Handle missing state (fallback or error)
        state = ConversationState()
```

### Updating State

```python
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Get current state
    task_state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    state = ConversationState.model_validate(task_state.state)
    
    # Modify state
    state.turn_count += 1
    state.messages.append({
        "role": "user",
        "content": params.event.content.content,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Save updated state
    await adk.state.update(
        state_id=task_state.id,
        task_id=params.task.id,
        agent_id=params.agent.id,
        state=state,
        trace_id=params.task.id
    )
```


## Task/Agent Scoped State

!!! danger "Critical for Multi-Agent Systems"
    **State is scoped per (task_id, agent_id) pair.** This isolation is fundamental to Agentex's ability to run multiple agents in parallel without conflicts.

### The Core Principle

Each **unique combination** of `(task_id, agent_id)` gets its own isolated state storage:

```python
# These are all SEPARATE state instances:
state_1 = (task_id="task_123", agent_id="agent_A")  # Agent A working on Task 123
state_2 = (task_id="task_123", agent_id="agent_B")  # Agent B working on Task 123  
state_3 = (task_id="task_456", agent_id="agent_A")  # Agent A working on Task 456
state_4 = (task_id="task_456", agent_id="agent_B")  # Agent B working on Task 456
```

### Why State Isolation Matters

#### ✅ Enables Parallel Multi-Agent Workflows

```python
# Task "customer_support_123" with multiple specialized agents
# Each agent maintains separate, isolated state:

# Customer Support Agent state
support_state = {
    "customer_tier": "premium",
    "issue_category": "billing", 
    "escalation_level": 1,
    "previous_interactions": [...]
}

# Technical Diagnostics Agent state
diagnostics_state = {
    "tests_completed": ["network_ping", "dns_lookup"],
    "error_codes": ["timeout_error"],
    "diagnostic_stage": "investigating_firewall"
}

# Both work on the same task simultaneously without interference
await adk.state.create(task_id="customer_support_123", agent_id="support-agent", state=support_state)
await adk.state.create(task_id="customer_support_123", agent_id="diagnostics-agent", state=diagnostics_state)
```

#### ✅ Simplifies Agent Logic

Each agent only needs to understand **its own state**:

```python
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Agent only cares about its own state - simple!
    my_state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id  # Only MY state
    )
    
    # Simple logic - no coordination needed
    if my_state.state.get("analysis_complete"):
        await send_final_report()
    else:
        await continue_analysis()
```

#### ✅ Prevents State Conflicts

```python
# Multiple agents can update their state simultaneously without conflicts
async def agent_a_work(task_id: str):
    state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id="agent_a")
    state.state["progress"] = "analyzing_data"
    await adk.state.update(state_id=state.id, state=state.state)

async def agent_b_work(task_id: str):
    state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id="agent_b") 
    state.state["progress"] = "generating_report"
    await adk.state.update(state_id=state.id, state=state.state)

# These run in parallel - no conflicts because state is isolated
await asyncio.gather(
    agent_a_work("task_123"),
    agent_b_work("task_123")
)
```

## State Access Patterns

#### ✅ Correct: Agent-Scoped State Access

```python
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # Always scope state to the current agent
    my_state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id  # Current agent's ID
    )
    
    if my_state:
        # Update my own state
        my_state.state["last_processed"] = datetime.now().isoformat()
        await adk.state.update(state_id=my_state.id, state=my_state.state)
    else:
        # Create initial state for this agent on this task
        await adk.state.create(
            task_id=params.task.id,
            agent_id=params.agent.id,
            state={"initialized": True}
        )
```

#### ❌ Wrong: Trying to Access Other Agent's State

```python
# WRONG: Don't try to access other agents' state directly
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    # This violates the isolation principle
    other_agent_state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id="some_other_agent"  # ❌ Don't do this
    )
```

#### ✅ Correct: Agent Coordination via Messages

If agents need to coordinate, use the shared message ledger:

```python
# Agent A signals completion via message
@acp.on_task_event_send
async def agent_a_handler(params: SendEventParams):
    # Complete analysis
    analysis_result = await perform_analysis()
    
    # Signal to other agents via shared message ledger
    await adk.messages.create(
        task_id=params.task.id,
        content=DataContent(
            author=MessageAuthor.AGENT,
            data={
                "agent": "analyst",
                "status": "analysis_complete", 
                "results": analysis_result
            }
        )
    )

# Agent B reacts to signal from message ledger
@acp.on_task_event_send  
async def agent_b_handler(params: SendEventParams):
    # Check message ledger for coordination signals
    messages = await adk.messages.list(task_id=params.task.id)
    
    analysis_messages = [
        msg for msg in messages 
        if msg.content.type == TaskMessageContentType.DATA 
        and msg.content.data.get("agent") == "analyst"
        and msg.content.data.get("status") == "analysis_complete"
    ]
    
    if analysis_messages:
        # Agent A is done - start my work
        await generate_report(analysis_messages[-1].content.data["results"])
```

## Multi-Agent Collaboration Example

```python
# Data Analysis Task with 3 Specialized Agents

# Agent 1: Data Validator
class DataValidatorAgent:
    async def process(self, task_id: str, agent_id: str):
        # My state: validation progress
        state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id=agent_id)
        state.state.update({
            "validation_stage": "checking_data_quality",
            "rows_validated": 1500,
            "errors_found": []
        })
        await adk.state.update(state_id=state.id, state=state.state)

# Agent 2: Statistical Analyzer  
class StatisticalAnalyzerAgent:
    async def process(self, task_id: str, agent_id: str):
        # My state: analysis progress
        state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id=agent_id)
        state.state.update({
            "analysis_stage": "computing_correlations",
            "models_tested": ["linear", "polynomial"],
            "best_model_r2": 0.85
        })
        await adk.state.update(state_id=state.id, state=state.state)

# Agent 3: Report Generator
class ReportGeneratorAgent:
    async def process(self, task_id: str, agent_id: str):
        # My state: report progress  
        state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id=agent_id)
        state.state.update({
            "report_stage": "generating_visualizations",
            "charts_completed": ["correlation_matrix", "distribution_plots"],
            "pending_sections": ["conclusions", "recommendations"]
        })
        await adk.state.update(state_id=state.id, state=state.state)

# All three agents work in parallel, each maintaining isolated state
# Coordination happens through the shared message ledger, not shared state
```

## Common Mistakes

### 1. Trying to Share State Between Agents

```python
# WRONG: Attempting to share state
shared_state = {
    "agent_a_progress": 50,
    "agent_b_progress": 75  
}
# This violates the isolation principle
```

### 2. Not Scoping State Properly

```python
# WRONG: Missing agent_id in state operations
state = await adk.state.get_by_task(task_id=task_id)  # This doesn't exist!

# CORRECT: Always include both task_id and agent_id
state = await adk.state.get_by_task_and_agent(task_id=task_id, agent_id=agent_id)
```

### 3. Coordination Through State Instead of Messages

```python
# WRONG: Using state for coordination
my_state.state["signal_to_other_agent"] = "analysis_complete"  # Other agents can't see this

# CORRECT: Use messages for coordination
await adk.messages.create(
    task_id=task_id,
    content=DataContent(author=MessageAuthor.AGENT, data={"signal": "analysis_complete"})
)
```

## Key Takeaway

!!! info "Remember the Design"
    - **State is private** to each `(task_id, agent_id)` combination
    - **Agents work independently** with their own isolated state
    - **Coordination happens through messages**, not shared state
    - **This design enables** parallel execution and simple agent logic 