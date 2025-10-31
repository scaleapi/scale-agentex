# Types Reference

Comprehensive API reference for all core object types in Agentex. These types are automatically generated from the source code.

## ACP Parameters

### CreateTaskParams

::: agentex.lib.types.acp.CreateTaskParams

### SendMessageParams

::: agentex.lib.types.acp.SendMessageParams

### SendEventParams

::: agentex.lib.types.acp.SendEventParams

### CancelTaskParams

::: agentex.lib.types.acp.CancelTaskParams

## Agent

::: agentex.types.agent.Agent


### ACPType

::: agentex.types.acp_type.AcpType


## Task

::: agentex.types.task.Task


## TaskMessage

::: agentex.types.task_message.TaskMessage

::: agentex.types.task_message_content.TaskMessageContent
    options:
      show_source: false
      show_root_heading: true
      show_root_toc_entry: false
      heading_level: 3

#### TextContent

::: agentex.types.text_content.TextContent

#### DataContent

::: agentex.types.data_content.DataContent

#### ToolRequestContent

::: agentex.types.tool_request_content.ToolRequestContent  

#### ToolResponseContent

::: agentex.types.tool_response_content.ToolResponseContent


::: agentex.types.task_message_update.TaskMessageUpdate
    options:
      show_source: false
      show_root_heading: true
      show_root_toc_entry: false
      heading_level: 3


#### StreamTaskMessageStart

::: agentex.types.task_message_update.StreamTaskMessageStart

#### StreamTaskMessageDelta

::: agentex.types.task_message_update.StreamTaskMessageDelta

#### StreamTaskMessageFull

::: agentex.types.task_message_update.StreamTaskMessageFull

#### StreamTaskMessageDone

::: agentex.types.task_message_update.StreamTaskMessageDone

::: agentex.types.task_message_update.TaskMessageDelta
    options:
        show_source: false
        show_root_heading: true
        show_root_toc_entry: false
        heading_level: 3


#### TextDelta

::: agentex.types.text_delta.TextDelta

#### DataDelta

::: agentex.types.data_delta.DataDelta

#### ToolRequestDelta

::: agentex.types.tool_request_delta.ToolRequestDelta

#### ToolResponseDelta

::: agentex.types.tool_response_delta.ToolResponseDelta

## Event

::: agentex.types.event.Event

## State

::: agentex.types.state.State


## Usage Examples

For practical usage examples and patterns, see:

- [Task Concepts](../concepts/task.md) - Understanding tasks and their lifecycle
- [TaskMessage Concepts](../concepts/task_message.md) - Working with messages
- [Streaming Concepts](../concepts/streaming.md) - Real-time message streaming
- [State Concepts](../concepts/state.md) - Managing persistent state
- [Agent-to-Client Protocol (ACP)](../acp/overview.md) - Sync and Async ACP handler parameters explained

 