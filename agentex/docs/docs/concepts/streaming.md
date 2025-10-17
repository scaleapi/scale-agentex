# Streaming Concepts

Streaming enables real-time delivery of messages as they're being generated, providing responsive user experiences for long-running operations like LLM text generation, data processing, or multi-step workflows.

## What is Streaming?

**Streaming** in Agentex allows agents to send partial message updates while processing, rather than waiting to send a complete response. This creates fluid, responsive interactions similar to ChatGPT's typing experience.

Key benefits:

- **Immediate feedback** - Users see progress instantly
- **Better UX** - No waiting for long operations to complete
- **Progressive disclosure** - Information appears as it's generated
- **Cancellation support** - Users can interrupt long operations

## Streaming Types

### TaskMessageUpdate

The base type for all streaming updates:

```python
from agentex.lib.types.task_message_updates import (
    TaskMessageUpdate,
    TaskMessageUpdateType,
    StreamTaskMessageStart,
    StreamTaskMessageDelta,
    StreamTaskMessageFull,
    StreamTaskMessageDone
)

# Streaming follows this sequence:
# 1. START - Begin streaming message
# 2. DELTA - Incremental content updates (multiple)
# 3. FULL - Complete message content (optional)
# 4. DONE - Streaming complete
```

### Streaming Lifecycle

```python
async def stream_response() -> AsyncGenerator[TaskMessageUpdate, None]:
    """Example streaming response generator"""
    
    # 1. Start streaming
    yield StreamTaskMessageStart(
        index=0,
        content=TextContent(
            author=MessageAuthor.AGENT,
            content="",  # Start with empty content
            format=TextFormat.PLAIN
        )
    )
    
    # 2. Send incremental updates
    response_parts = ["Hello", " there!", " How can I help you today?"]
    
    for part in response_parts:
        yield StreamTaskMessageDelta(
            index=0,
            delta=TextDelta(text_delta=part)
        )
        await asyncio.sleep(0.1)  # Simulate processing time
    
    # 3. Mark as complete
    yield StreamTaskMessageDone(index=0)
```

## Stream Implementation Patterns

### Sync ACP Streaming

For simple request-response patterns:

```python
@acp.on_message_send
async def handle_message_send(params: SendMessageParams) -> AsyncGenerator[TaskMessageUpdate, None]:
    """Streaming response in Sync ACP"""
    
    user_input = params.content.content
    
    # Start streaming
    yield StreamTaskMessageStart(
        index=0,
        content=TextContent(
            author=MessageAuthor.AGENT,
            content="",
            format=TextFormat.MARKDOWN
        )
    )
    
    # Generate response with streaming
    async for chunk in generate_streaming_response(user_input):
        yield StreamTaskMessageDelta(
            index=0,
            delta=TextDelta(text_delta=chunk)
        )
    
    # Complete the stream
    yield StreamTaskMessageDone(index=0)

async def generate_streaming_response(input_text: str) -> AsyncGenerator[str, None]:
    """Example LLM streaming integration"""
    
    # OpenAI streaming example
    response = await openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": input_text}],
        stream=True
    )
    
    async for chunk in response:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

### Agentic ACP Streaming

For event-driven workflows:

```python
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    """Streaming in Agentic ACP"""
    
    # Use ADK streaming module for manual control
    stream = adk.streaming.create_stream(
        task_id=params.task.id,
        index=0
    )
    
    # Start streaming
    await stream.start(
        content=TextContent(
            author=MessageAuthor.AGENT,
            content="Processing your request...",
            format=TextFormat.MARKDOWN
        )
    )
    
    try:
        # Process in steps with updates
        await stream.update(delta=TextDelta(text_delta="\n\n## Step 1: Analyzing data..."))
        analysis_result = await analyze_data(params.event.content)
        
        await stream.update(delta=TextDelta(text_delta="\n✅ Analysis complete"))
        await stream.update(delta=TextDelta(text_delta="\n\n## Step 2: Generating recommendations..."))
        
        recommendations = await generate_recommendations(analysis_result)
        await stream.update(delta=TextDelta(text_delta="\n✅ Recommendations ready"))
        
        # Send final results
        await stream.update(delta=TextDelta(
            text_delta=f"\n\n## Results\n\n{format_results(recommendations)}"
        ))
        
    finally:
        # Always complete the stream
        await stream.complete()
```

## Advanced Streaming Patterns

**Multi-Stage Processing** - Stream progress updates for complex workflows with multiple steps
**Parallel Streaming** - Combine results from concurrent operations (weather, news, stocks) and stream as they complete
**Streaming with State** - Update agent state while streaming responses to maintain conversation context

## Error Handling in Streaming

Always wrap streaming operations in try/finally blocks to ensure streams complete properly:

```python
stream = adk.streaming.create_stream(task_id=params.task.id, index=0)

try:
    await stream.start(content=TextContent(...))
    result = await risky_operation()
    await stream.update(delta=TextDelta(text_delta=f"✅ {result}"))
except Exception as e:
    await stream.update(delta=TextDelta(text_delta=f"❌ Error: {str(e)}"))
finally:
    await stream.complete()  # Always complete
```

## Performance & Best Practices

**Batch updates** - Buffer small chunks instead of streaming every character
**Memory management** - Process large datasets in chunks, avoid loading everything
**Always complete streams** - Use try/finally to ensure `stream.complete()` is called
**Clear progress** - Show step numbers and estimated completion time
**Graceful errors** - Stream error messages instead of silent failures

## API Reference

For complete type definitions, see:

::: agentex.types.task_message_update.TaskMessageUpdate

::: agentex.types.task_message_update.StreamTaskMessageDelta

::: agentex.types.text_delta.TextDelta

## Next Steps

- Learn about [State Concepts](state.md) for persistent data during streaming
- Explore [Advanced Streaming Concepts](callouts/streaming.md) for complex streaming patterns
- See [TaskMessage Concepts](task_message.md) for message structure 