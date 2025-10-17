# Architecture

React component library for Agentex with hierarchical contexts and agent communication.

## Key Folders

```text
/registry/agentex/          # Source code for published components
  /agentex-root             # Global context (agents, tasks, SDK client)
  /agentex-task             # Task context (messages, communication)

/public/r/                  # Published component definitions (JSON)
/components/                # Private UI components + shadcn/ui base
/entrypoints/               # Single-page applications

registry.json               # Defines what from /registry/ is put into /public/r/
```

## State Architecture

**Two-tier hierarchy:**

- `AgentexRoot` → Global state (agents, tasks, pending messages)
- `AgentexTask` → Task-specific state (messages, deltas)

**Three-layer pattern:**

- **Views** - React components that read from Zustand stores (reactive)
- **ViewControllers** - Read stores + decide which view to show (conditional rendering)  
- **Controllers** - Use store API imperatively, handle all async operations

## Agent Types

1. **Sync ACP** - `message/send` RPC, streaming responses
2. **Agentic ACP** - `event/send` RPC, fire-and-forget events

## Key Controllers

**AgentexRootController:**

- `createTask()` - Create tasks + queue pending messages
- `popPendingMessageForTask()` - Thread-safe pending message handling

**AgentexTaskController:**

- `sendMessage()` - Route messages by agent type
- `isSendMessageEnabled` - Control when messaging is allowed

## Tech Stack

- Next.js 15, React 19, Zustand, Tailwind v4, Radix UI
- Component distribution via shadcn/ui pattern
