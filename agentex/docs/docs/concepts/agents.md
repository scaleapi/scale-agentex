# Agent Concepts

Agents are the core building blocks of Agentex applications. Understanding what agents are and how they work is essential for building effective AI systems.

## What is an Agent?

In Agentex, this of **an Agent as just code** - specifically, it is just Python code that adheres to the Agent-to-Client Protocol (ACP). This allows clients to speak to any agent the same way regardless of the agent's complexity. This allows agent developers full unopinionated control over which libraries they use, which models they use, and how they implement their business logic.

An agent defines:

- **Handler functions** that respond to events (messages, task creation, etc.)
- **Business logic** for processing user requests
- **State management** for maintaining context across interactions
- **Integration code** for calling external services, APIs, or models

Think of an agent like a **web server endpoint** - it receives requests, processes them using your code, and returns responses. The difference is that agents are designed specifically for conversational AI and can maintain state across multiple interactions.

!!! note "Agents Are Not LLMs"
    An agent is **your application code**, not an LLM. While agents often call LLMs (like OpenAI's API), the agent itself is the Python code you write to orchestrate the conversation, manage state, and implement your business logic.

## Development Principles

Agentex was built around five core development principles that shape how you build and deploy agents:

### 1. Agents are just code
Your agents are simply Python functions - no vendor lock-in, no proprietary frameworks, just code you control.

### 2. Code is unopinionated and usable with any library  
Use any Python library, any LLM provider, any database, any framework. Agentex doesn't constrain your technology choices.

### 3. Local Development is fast and easy
Develop and test your agents locally with minimal setup. No complex infrastructure required for development.

### 4. Both simple sync and complex async use cases are supported
Whether you need simple request-response patterns or complex multi-step workflows, Agentex supports your use case.

### 5. All agents can be called with a unified communication protocol
Regardless of complexity, all agents use the same client interface. Simple agents and complex workflows look identical to clients.

### Focus on Business Logic Only

**The primary tenet of Agentex is that agent developers should focus exclusively on business logic.** Everything else is handled automatically:

#### What Agentex Handles for You:

- **Containerization**: Automatically package agents with your custom dependencies
- **Hosting**: Host agents on any cloud provider (calleable by unique name)
- **Scaling**: Scale up or down based on demand and usage patterns
- **Secrets Management**: Credentials are securely injected as environment variables
- **Streaming**: Stream real-time messages to clients even in asynchronous environments
- **Data Persistence**: Message history, state management, and conversation storage
- **Distributed Work**: Distributed work asynchronously using natively-supported Temporal
- **Reliability**: Error handling, retries, and fault tolerance with Temporal

#### What You Focus On:

- **Business Logic**: Your core agent functionality and workflows
- **Integration Code**: Connecting to your APIs, databases, and services
- **User Experience**: Designing conversation flows and responses
- **Domain Expertise**: Implementing your specific use case requirements

The Agentex service, along with its Agent Development Kit (ADK) and SDK, was built on carefully selected software and infrastructure that abstracts away these operational complexities. This allows you to deploy production-ready agents without becoming an infrastructure expert.

## Agent Implementation by ACP Type

The way you implement agents depends on which ACP (Agent-to-Client Protocol) type you choose. Read more about the ACP types in the [ACP](../acp/overview.md) section. Here is a quick overview of the two ACP types:

**Sync ACP** agents are the simplest form - just a single function that processes messages and returns responses.

**Agentic ACP** agents have multiple handler functions that manage the complete interaction lifecycle.

## Agent Relationships

!!! info "For Detailed Implementation"
    This section explains the architectural relationships between agents and other Agentex entities. For specific implementation patterns, refer to the [Agent Client Protocol guides](../acp/overview.md).

### Agent ↔ Tasks (Many-to-Many)

**A single agent can handle multiple tasks simultaneously, and a single task can involve multiple agents.**

#### Single Agent, Multiple Tasks

Your agent code runs independently for each task:

```python
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # This same function handles messages from many different tasks
    task_id = params.task.id  # Different for each conversation
    
    # Each task gets independent processing
    response = await process_for_task(task_id, params.content)
    return response
```

#### Multiple Agents, Single Task

Different agents can contribute to the same conversation:

```python
# Task "task_123" message history might include:
messages = [
    {"author": "USER", "content": "Analyze this data and create a report"},
    {"author": "AGENT", "content": "Starting analysis...", "agent_id": "data-analyst"},
    {"author": "AGENT", "content": "Analysis complete", "agent_id": "data-analyst"},
    {"author": "AGENT", "content": "Generating report...", "agent_id": "report-generator"},
    {"author": "AGENT", "content": "Report ready!", "agent_id": "report-generator"}
]
```

This enables **multi-agent workflows** where specialized agents collaborate on complex tasks.

### Agent ↔ State (One-to-One per Task)

**Each agent maintains its own isolated state for each task it's working on.**

#### Key Characteristics:

- **Scoped Storage**: State is isolated by `(task_id, agent_id)` pairs
- **Independent Operation**: Agents don't interfere with each other's state
- **Simple Management**: Each agent only needs to understand its own state
- **Parallel Safety**: Multiple agents can work simultaneously without conflicts

#### State Isolation Example:

```python
# Same task, different agents, separate states:

# Customer Support Agent state
support_state = {
    "customer_tier": "premium",
    "issue_category": "billing",
    "escalation_level": 1
}

# Technical Agent state  
tech_state = {
    "diagnostic_stage": "network_check",
    "test_results": ["ping_ok", "dns_ok"],
    "next_steps": ["check_firewall"]
}

# Both agents work on task_123 but maintain separate state
await adk.state.create(task_id="task_123", agent_id="support-agent", state=support_state)
await adk.state.create(task_id="task_123", agent_id="tech-agent", state=tech_state)
```

### Agent ↔ Messages (Many-to-Many)

**Agents can read all messages in a task and create messages marked with the AGENT author type.**

!!! note "Agent Identification in Messages"
    Currently, messages are not tagged with the specific agent that created them. In the future, Agentex will support providing the name of the agent that produced each message, enabling better tracking in multi-agent scenarios.

#### Message Creation:

```python
# Sync ACP - Return messages directly
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    return TextContent(
        author=MessageAuthor.AGENT,
        content="Hello from the agent!"
    )

# Agentic ACP - Create messages explicitly
@acp.on_task_event_send
async def handle_event_send(params: SendEventParams):
    await adk.messages.create(
        task_id=params.task.id,
        content=TextContent(
            author=MessageAuthor.AGENT,
            content="Processing your request..."
        )
    )
```

#### Message Reading:

```python
# Agents can read all messages in a task
all_messages = await adk.messages.list(task_id=task_id)

# Filter messages by author type
user_messages = [msg for msg in all_messages if msg.content.author == MessageAuthor.USER]
agent_messages = [msg for msg in all_messages if msg.content.author == MessageAuthor.AGENT]
```

### Agent ↔ External Systems

**Agents are your integration layer** - they connect Agentex conversations to your existing systems:

```python
import os

@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    user_message = params.content.content
    
    # Agents typically integrate with:
    
    # 1. LLM APIs (using environment variables for API keys)
    openai_api_key = os.getenv("OPENAI_API_KEY")
    llm_response = await openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_message}]
    )
    
    # 2. Databases (using environment variables for connection strings)
    database_url = os.getenv("DATABASE_URL")
    user_data = await database.get_user_profile(params.task.user_id)
    
    # 3. External APIs (using environment variables for credentials)
    weather_api_key = os.getenv("WEATHER_API_KEY")
    weather_data = await weather_api.get_current_weather(location)
    
    # 4. Internal services
    analysis_result = await internal_analytics_service.analyze(data)
    
    # Combine results into response
    response = f"Based on the data: {llm_response.choices[0].message.content}"
    
    return TextContent(
        author=MessageAuthor.AGENT,
        content=response
    )
```

All credentials and secrets are securely provided as environment variables by Agentex. For more details on secrets management, see the [Deployment Commands](../deployment/commands.md#agentex-secrets-sync) reference.

## Core Principles

### 1. Agents Are Stateless Functions (By Default)

```python
# Good: Stateless agent function
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # No global variables, no shared state
    response = await process_message(params.content.content)
    return TextContent(author=MessageAuthor.AGENT, content=response)

# Avoid: Global state that persists across calls
conversation_history = []  # Don't do this!

@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    conversation_history.append(params.content)  # Problematic!
```

### 2. Use Agentex State for Persistence

```python
# Good: Use Agentex state management
@acp.on_message_send
async def handle_message_send(params: SendMessageParams):
    # Get state from Agentex
    state = await adk.state.get_by_task_and_agent(
        task_id=params.task.id,
        agent_id=params.agent.id
    )
    
    # Update state
    new_state = {"last_message": params.content.content}
    await adk.state.update(state_id=state.id, state=new_state)
```

## API Reference

For complete type definitions, see the [API - Types Reference](../api/types.md) 