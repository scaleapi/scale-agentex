# Implementation Guide

## Critical Implementation Considerations

### Deterministic Replay Requirements

❌ **Avoid in workflows:**
```python
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def bad_workflow_handler(self, params):
    current_time = datetime.now()  # Non-deterministic!
    random_id = uuid.uuid4()       # Non-deterministic!
    api_response = requests.get()  # Side effect!
```

✅ **Correct approach:**
```python
@workflow.signal(name=SignalName.RECEIVE_EVENT)
async def good_workflow_handler(self, params):
    current_time = workflow.now()           # Deterministic
    random_id = workflow.uuid4()            # Deterministic
    # Side effects go through Agentex ADK (activities)
    await adk.messages.create(...)
```

### Activity vs Workflow Boundaries

- **Workflows**: Pure, deterministic business logic
- **Activities**: All external interactions (APIs, databases, file I/O)

### Common Implementation Issues

#### Data Serialization Limits
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

#### Workflow State Size Explosion
```python
# ❌ Don't accumulate unbounded state
async def bad_workflow():
    all_responses = []  # This grows forever!
    while True:
        response = await get_response()
        all_responses.append(response)  # Memory leak in workflow state
```

**Why**: Workflow state is replayed from the beginning. Growing state = slower replays.

#### Activity Retry Idempotency
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

#### Async/Await in Wrong Places
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

**Why**: Non-Agentex async operations aren't tracked in event history and break deterministic replay.
