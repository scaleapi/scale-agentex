# Agent Development Kit (ADK) Reference

!!! info "ADK vs SDK"
    **ADK (Agent Development Kit)** - Use within agent code to interact with Agentex infrastructure (streaming, tracing, state management, etc.)

    **SDK (Software Development Kit)** - Use to make requests to the Agentex server via its REST API. [View SDK Docs →](https://agentex-sdk.stldocs.app/api/python)

This is the API reference for the Agentex Python ADK. Use this ADK to leverage convenient abstractions for interacting with clients through Agentex's Agentic Infrastructure. This ADK makes things like streaming, tracing, tool calling, and communicating with clients in an async manner easy.

## Agent Development Kit (ADK)

Use the following modules to interact with the core functionality of Agentex.

### `agentex.lib.adk.acp`

Use the following functions to interact with Agentex agents through the Agent 2 Client Protocol (ACP). Each agent handles standard ACP functions and can be communicated with through these methods.

::: agentex.lib.adk._modules.acp.ACPModule

### `agentex.lib.adk.tasks`

Use the following functions to perform CRUD operations on tasks in Agentex.

!!! warning
    Task creation is handled by the `agentex.lib.adk.acp` module, but you can use this module to get and delete tasks.

::: agentex.lib.adk._modules.tasks.TasksModule

### `agentex.lib.adk.messages`

Use the following functions to perform CRUD operations on messages in Agentex.

!!! warning
    Message creation here is pure CRUD, to send a message to an agent, use the `agentex.lib.adk.acp` module instead.

::: agentex.lib.adk._modules.messages.MessagesModule

### `agentex.lib.adk.state`

Use the following functions to perform CRUD operations on state in Agentex. State is uniquely identified by task and the agent that created it. The idea is that the agent is independently working on the task on its own and stores its working context in a state object for long-term memory.

::: agentex.lib.adk._modules.state.StateModule

### `agentex.lib.adk.streaming`

This is a low-level module that allows you to stream intermediate results to clients. Most high level `agentex.lib.adk.providers` modules handle streaming for you, but you can use this if you are using an unsupported provider or want to stream something that isn't supported by the high level modules.

::: agentex.lib.adk._modules.streaming.StreamingModule

### `agentex.lib.adk.tracing`

This is a low-level module that allows you to start and end spans in the trace. Most high level `agentex.lib.adk` modules handle tracing for you at the lowest levels, but if you want to build a hierarchy of trace spans (for better readability), you should create your own spans with this module, so you can group lower level traces together. Do this by assigning the `parent_span_id` of downstream functions to the spans you create.

::: agentex.lib.adk._modules.tracing.TracingModule

### `agentex.lib.adk.events`

Use the following functions to retrieve and list events in Agentex. Events represent activity within tasks and are useful for tracking agent interactions and system events.

::: agentex.lib.adk._modules.events.EventsModule

### `agentex.lib.adk.agent_task_tracker`

Use the following functions to manage agent task trackers in Agentex. Agent task trackers help monitor the processing status of agents working on specific tasks, including the last processed event ID and current status.

::: agentex.lib.adk._modules.agent_task_tracker.AgentTaskTrackerModule

## External Providers

These are the modules that handle external provider functionality. The conveniently wrap external provider functionality in a high level interface that is easy to use and already handles streaming, tracing, and other core functionality for you.

### `agentex.lib.adk.providers.openai`

Use the following module to interact with common OpenAI functions.

::: agentex.lib.adk.providers._modules.openai.OpenAIModule

### `agentex.lib.adk.providers.litellm`

Use the following module to interact with common LiteLLM functions.

::: agentex.lib.adk.providers._modules.litellm.LiteLLMModule

### `agentex.lib.adk.providers.sgp`

Use the following module to interact with common SGP functions.

::: agentex.lib.adk.providers._modules.sgp.SGPModule

## Utilities

These are utility modules used during AI development for example for formatting prompts and more.

### `agentex.lib.adk.utils.templating`

Use the following module to render Jinja templates.

::: agentex.lib.adk.utils._modules.templating.TemplatingModule
