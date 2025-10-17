# TaskMessages vs LLM Messages

!!! danger "Critical for LLM Integrations"
    **Agentex stores conversation history as `TaskMessages`, not LLM-compatible messages.** You must convert them to LLM-compatible format before sending to language models.

## Why This Split Exists

**Agentex stores conversation history as `TaskMessages`, not LLM-compatible messages.** This might seem duplicative, but the split between TaskMessage and LLMMessage is intentional and important.

**TaskMessages** are messages that are sent between an Agent and a Client. They are fundamentally decoupled from messages sent to the LLM. This is because you may want to send additional metadata to allow the client to render the message on the UI differently.

**LLMMessages** are OpenAI-compatible messages that are sent to the LLM, and are used to track the state of a conversation with a model.

### ❌ What Doesn't Work

```python
# WRONG: Trying to send TaskMessages directly to LLM
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # Get conversation history
    task_messages = await adk.messages.list(task_id=params.task.id)
    
    # This will FAIL - TaskMessages are not LLM-compatible
    response = await openai_client.chat.completions.create(
        model="gpt-4",
        messages=task_messages  # ERROR: Wrong format!
    )
```

### ✅ How It Actually Works

Always convert TaskMessages to LLM format:

```python
# CORRECT: Convert TaskMessages to LLM-compatible format
from agentex.lib.sdk.utils.messages import convert_task_messages_to_llm_messages

@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # Get conversation history as TaskMessages
    task_messages = await adk.messages.list(task_id=params.task.id)
    
    # Convert to LLM-compatible format
    llm_messages = convert_task_messages_to_llm_messages(task_messages)
    
    # Now safe to send to LLM
    response = await openai_client.chat.completions.create(
        model="gpt-4", 
        messages=llm_messages  # ✅ Correct format
    )
```

## Conversion Logic

### Simple Scenarios

In simple scenarios your conversion logic will just use the default converters:

```python
from agentex.lib.sdk.utils.messages import convert_task_messages_to_llm_messages

# Simple conversion using default converters
task_messages = await adk.messages.list(task_id=task_id)
llm_messages = convert_task_messages_to_llm_messages(task_messages)
```

### Complex Scenarios

However, in complex scenarios where you are leveraging the flexibility of the TaskMessage type to send non-LLM-specific metadata, you should write custom conversion logic.

**Some complex scenarios include:**

- **Postprocessing LLM Output**: Taking a markdown document output by an LLM, postprocessing it into a JSON object to clearly denote title, content, and footers. This can be sent as a `DataContent` TaskMessage to the client and converted back to markdown here to send back to the LLM.

- **Multi-LLM Workflows**: If using multiple LLMs (like in an actor-critic framework), you may want to send `DataContent` that denotes which LLM generated which part of the output and write conversion logic to split the TaskMessage history into multiple LLM conversations.

- **Internal LLM Conversations**: If using multiple LLMs, but one LLM's output should not be sent to the user (i.e. a critic model), you can leverage the State as an internal storage mechanism to store the critic model's conversation history. This is a powerful and flexible way to handle complex scenarios.

### Creating Custom TaskMessage Converters

For complex scenarios, implement the `TaskMessageConverter` base class to create custom conversion logic:

```python
from agentex.lib.sdk.utils.messages import TaskMessageConverter
from agentex.types.llm_messages import Message, AssistantMessage
from agentex.types.task_messages import TaskMessage
import json

class CustomDataContentConverter(TaskMessageConverter):
    """Custom converter for DataContent with structured metadata."""
    
    def convert(self, task_message: TaskMessage) -> Message:
        """Convert DataContent TaskMessage to LLM format with custom logic."""
        content = task_message.content
        
        # Convert structured data to readable format for LLM
        if isinstance(content.data, dict):
            formatted_content = f"Analysis: {json.dumps(content.data, indent=2)}"
        else:
            formatted_content = str(content.data)
        
        return AssistantMessage(content=formatted_content)

# Usage with custom converter
task_messages = await adk.messages.list(task_id=task_id)
llm_messages = convert_task_messages_to_llm_messages(
    task_messages,
    data_converter=CustomDataContentConverter()
)
```

## Common Mistakes

### Forgetting to Convert
```python
# WRONG: Direct usage without conversion
task_messages = await adk.messages.list(task_id=task_id)
response = await llm_client.chat_completion(messages=task_messages)  # Will fail!

# CORRECT: Convert first
llm_messages = convert_task_messages_to_llm_messages(task_messages)
response = await llm_client.chat_completion(messages=llm_messages)
```

### Manual Conversion
```python
# WRONG: Manual conversion (error-prone, especially for tool messages)
llm_messages = []
for task_msg in task_messages:
    llm_messages.append({
        "role": "user" if task_msg.content.author == "USER" else "assistant",
        "content": task_msg.content.content  # Missing tool call handling!
    })

# CORRECT: Use the provided utility
llm_messages = convert_task_messages_to_llm_messages(task_messages)
```

## Key Takeaway

!!! info "Remember the Rule"
    - **TaskMessages**: For Agentex operations (storage, retrieval, agent communication)
    - **LLM Messages**: For language model API calls (OpenAI, Anthropic, etc.)
    - **Always convert** between formats when crossing the boundary
    - **Use custom converters** for complex scenarios with metadata 