# State Machines in Agentex

State machines are a fundamental pattern in Agentex for managing complex workflows with multiple states and transitions. This document explains the core concepts and structure of the state machine SDK.

## Overview

A state machine in Agentex consists of:

- **States**: Defined as enums or strings that represent different phases of execution
- **Workflows**: The logic that executes when a state is active
- **Transitions**: Movement between states based on workflow execution results
- **Data**: Persistent data that flows through the state machine

## Core Classes

### StateMachine

The `StateMachine` class is the main orchestrator that manages state transitions and workflow execution.

```python
class StateMachine(ABC, Generic[T]):
    def __init__(
        self,
        initial_state: str,
        states: list[State],
        task_id: str | None = None,
        state_machine_data: T | None = None,
        trace_transitions: bool = False,
    ):
```

**Key Components:**

- `initial_state`: The starting state name
- `states`: List of all possible states with their associated workflows
- `task_id`: Required identifier for tracing and debugging (can be set later)
- `state_machine_data`: Generic data model that persists throughout execution
- `trace_transitions`: Enables detailed logging of state transitions

**Execution Flow:**

1. The state machine starts in the `initial_state`
2. It repeatedly calls `step()` until `terminal_condition()` returns `True`
3. Each `step()` executes the current state's workflow and transitions to the next state

### State

A `State` represents a single phase in the state machine with an associated workflow:

```python
class State(BaseModel):
    name: str
    workflow: StateWorkflow
```

**Components:**
- `name`: Unique identifier for the state
- `workflow`: The `StateWorkflow` instance that contains the execution logic

### StateWorkflow

`StateWorkflow` is an abstract base class that defines the interface for state execution logic:

```python
class StateWorkflow(ABC):
    @abstractmethod
    async def execute(
        self, state_machine: "StateMachine", state_machine_data: BaseModel | None = None
    ) -> str:
        pass
```

**Key Methods:**
- `execute()`: Runs the workflow logic and returns the name of the next state to transition to

## State Transitions and Execution

### How State Transitions Work

1. **Current State Retrieval**: The state machine gets the current state
2. **Workflow Execution**: Calls `execute()` on the current state's workflow
3. **Next State Determination**: The workflow returns the name of the next state
4. **Transition**: The state machine moves to the new state

```python
async def step(self) -> str:
    current_state_name = self.get_current_state()
    current_workflow = self.get_current_workflow()
    
    next_state_name = await current_workflow.execute(
        state_machine=self, state_machine_data=self.state_machine_data
    )
    
    await self.transition(next_state_name)
    return next_state_name
```

### Workflow Execution

Each workflow's `execute()` method:

- Receives the state machine instance and current data
- Performs the state-specific logic
- Returns the name of the next state to transition to

**Example Workflow:**
```python
class MyWorkflow(StateWorkflow):
    async def execute(
        self, state_machine: "StateMachine", state_machine_data: BaseModel | None = None
    ) -> str:
        # Perform state-specific logic
        result = await self.process_data(state_machine_data)
        
        # Determine next state based on result
        if result.is_success():
            return "next_state"
        else:
            return "error_state"
```

## State Definition and Mapping

### Defining States

States are typically defined as enums or constants and mapped to workflows:

```python
from enum import Enum

class MyStates(str, Enum):
    START = "start"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"

# Define workflows for each state
start_workflow = StartWorkflow()
processing_workflow = ProcessingWorkflow()
complete_workflow = NoOpWorkflow()  # Terminal state
error_workflow = ErrorWorkflow()

# Create State objects
states = [
    State(name=MyStates.START, workflow=start_workflow),
    State(name=MyStates.PROCESSING, workflow=processing_workflow),
    State(name=MyStates.COMPLETE, workflow=complete_workflow),
    State(name=MyStates.ERROR, workflow=error_workflow),
]
```

### State Machine Initialization

```python
class MyStateMachine(StateMachine[MyDataModel]):
    async def terminal_condition(self) -> bool:
        return self.get_current_state() == MyStates.COMPLETE

# Initialize the state machine
state_machine = MyStateMachine(
    initial_state=MyStates.START,
    states=states,
    state_machine_data=MyDataModel(),
    trace_transitions=True
)
```

## Data Flow

### State Machine Data

The `state_machine_data` parameter is a generic Pydantic model that persists throughout the entire state machine execution:

```python
class MyDataModel(BaseModel):
    input_data: str
    processed_results: list[str] = []
    error_message: str | None = None
```

### Data Access in Workflows

Workflows can access and modify the state machine data:

```python
class ProcessingWorkflow(StateWorkflow):
    async def execute(
        self, state_machine: "StateMachine", state_machine_data: MyDataModel | None = None
    ) -> str:
        if state_machine_data:
            # Access and modify the data
            result = await self.process(state_machine_data.input_data)
            state_machine_data.processed_results.append(result)
            
            return "complete"
        return "error"
```

## Persistence and Serialization

### Saving State

The state machine can be serialized to a dictionary for persistence:

```python
saved_state = state_machine.dump()
# Returns: {
#     "task_id": "task_123",
#     "current_state": "processing",
#     "initial_state": "start",
#     "state_machine_data": {...},
#     "trace_transitions": True
# }
```

### Loading State

A state machine can be restored from saved data:

```python
restored_machine = await MyStateMachine.load(saved_state, states)
```

## Tracing and Debugging

### Transition Tracing

When `trace_transitions=True`, the state machine logs detailed information about each transition:

- Input state and data
- Output state and data
- Transition timing
- Task correlation

### Task ID Management

The `task_id` is used for correlating traces and debugging. In Temporal workflows, the task_id is often not known until the task handler function receives the task, so you can initialize the state machine without it and set it later:

```python
# Initialize state machine without task_id
state_machine = MyStateMachine(
    initial_state=MyStates.START,
    states=states,
    state_machine_data=MyDataModel(),
    trace_transitions=True
)

# Set task_id when you receive the task in your handler
async def handle_task(task: Task) -> TaskResult:
    state_machine.set_task_id(task.task_id)
    # ... rest of your task handling logic
```

**Important:** The task_id is required for tracing to work properly. If you enable `trace_transitions=True` but don't set a task_id, the state machine will raise a `ClientError` when trying to trace transitions.

## Terminal Conditions

The state machine runs until `terminal_condition()` returns `True`. This method must be implemented by subclasses:

```python
class MyStateMachine(StateMachine[MyDataModel]):
    async def terminal_condition(self) -> bool:
        current_state = self.get_current_state()
        return current_state in ["complete", "error"]
```

## Common Patterns

### Terminal States

Use `NoOpWorkflow` for states that don't perform any action:

```python
complete_state = State(name="complete", workflow=NoOpWorkflow())
```

### Error Handling

Create dedicated error states and workflows:

```python
class ErrorWorkflow(StateWorkflow):
    async def execute(self, state_machine, state_machine_data):
        # Log error, cleanup, etc.
        return "complete"  # or stay in error state
```

### Conditional Transitions

Workflows can implement complex logic to determine the next state:

```python
class DecisionWorkflow(StateWorkflow):
    async def execute(self, state_machine, state_machine_data):
        if state_machine_data.needs_more_processing():
            return "processing"
        elif state_machine_data.has_errors():
            return "error"
        else:
            return "complete"
```

This foundation provides a robust, type-safe, and traceable framework for building complex workflows in Agentex applications.

## Related Documentation

- **[State Machine Tutorial](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials/10_agentic/10_temporal/020_state_machine)**: See how state machines are used in practice with the deep research agent tutorial 