# State Concepts

State provides persistent, task-scoped storage for agents, enabling memory across interactions and complex workflow management.

## What is State?

**State** in Agentex is persistent data storage uniquely associated with a specific task and agent combination. It allows agents to:

- **Remember context** across multiple interactions
- **Track workflow progress** through multi-step processes  
- **Store user preferences** and personalization data
- **Maintain session data** for complex conversations

State persists even if the agent process restarts.

## State Identity

State is uniquely identified by `(task_id, agent_id)`:

```python
# Each (task_id, agent_id) pair has exactly one state
task_123_agent_a = ("task-123", "agent-a")  # Agent A's state for task 123
task_123_agent_b = ("task-123", "agent-b")  # Agent B's state for task 123
```

## Basic State Operations

### Creation

```python
@acp.on_task_create
async def handle_task_create(params: CreateTaskParams):
    initial_state = {
        "conversation_started": datetime.utcnow().isoformat(),
        "interaction_count": 0,
        "user_preferences": {}
    }
    
    await adk.state.create(
        task_id=params.task.id,
        agent_id=params.agent.id,
        state=initial_state
    )
```

### Retrieval

```python
@acp.on_message_send  
async def handle_message_send(params: SendMessageParams):
    state_record = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    if state_record:
        current_state = state_record.state
        # Process with context
    else:
        # Handle first interaction
        pass
```

### Updates

```python
async def update_conversation_state(task_id: str, agent_id: str, user_input: str):
    state_record = await adk.state.get_by_task_and_agent(task_id, agent_id)
    
    if state_record:
        state = state_record.state
        state["interaction_count"] += 1
        state["last_message"] = user_input
        
        await adk.state.update(
            state_id=state_record.id,
            state=state
        )
```


## Limitations

### State Size Limit

Agentex state has a **16 megabyte (16MB)** storage limit per state object. This applies to the entire JSON-serialized state for a specific `(task_id, agent_id)` combination.

```python
# ✅ Good: Appropriate state size
state = {
    "conversation": {
        "turn_count": 42,
        "topic": "customer_support",
        "context": "user needs help with billing"
    },
    "user_profile": {
        "preferences": {"language": "en", "timezone": "UTC"},
        "tier": "premium"
    },
    "workflow_progress": {
        "current_step": "gathering_info",
        "completed_steps": ["greeting", "authentication"]
    }
}

# ❌ Avoid: Large data that approaches limits
state = {
    "full_document_content": "...",  # Could be MBs of text
    "image_data": b"...",            # Binary data
    "massive_conversation_log": [...] # Thousands of detailed entries
}
```

### Managing Large Data

For data that might exceed the 16MB limit, consider these strategies:

#### 1. Data Pruning

```python
async def prune_conversation_history(state: dict, max_entries: int = 50):
    """Keep only recent conversation history"""
    if "conversation" in state and "history" in state["conversation"]:
        history = state["conversation"]["history"]
        if len(history) > max_entries:
            state["conversation"]["history"] = history[-max_entries:]
    return state
```

#### 2. External Storage References

!!! note "Support Coming Soon"
    First class support for external storage references is coming soon. Please reach out to the maintainers of Agentex for feature requests.

```python
# Store large data externally, reference by ID
state = {
    "conversation_summary": "User discussed billing issues...",
    "external_data_refs": {
        "full_transcript": "s3://bucket/transcript-{task_id}.json",
        "documents": ["doc-123", "doc-456"]
    }
}

# Retrieve large data when needed
async def get_full_transcript(task_id: str) -> dict:
    state_record = await adk.state.get_by_task_and_agent(task_id, agent_id)
    transcript_ref = state_record.state["external_data_refs"]["full_transcript"]
    return await external_storage.load(transcript_ref)
```

#### 3. State Compression

```python
import json
import gzip
import base64

async def compress_large_state_field(data: dict) -> str:
    """Compress large data within state"""
    json_str = json.dumps(data)
    compressed = gzip.compress(json_str.encode('utf-8'))
    return base64.b64encode(compressed).decode('utf-8')

async def decompress_state_field(compressed_data: str) -> dict:
    """Decompress state data"""
    compressed = base64.b64decode(compressed_data.encode('utf-8'))
    json_str = gzip.decompress(compressed).decode('utf-8')
    return json.loads(json_str)
```


## API Reference

For complete type definitions, see the [API - Types Reference](../api/types.md)
