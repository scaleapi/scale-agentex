# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

### Development

- `npm run dev` - Start local development server with Turbopack (Next.js 15)
- `npm install` - Install dependencies
- `npm run build` - Build for production
- `npm run start` - Start production server

### Code Quality

- `npm run lint` - Run ESLint
- `npm run typecheck` - Run TypeScript type checking (use `tsc --noEmit`)
- `npm run test` - Run Jest tests
- `npm run storybook` - Start Storybook development server
- `npm run build-storybook` - Build Storybook for production

### Component Management

- `npx shadcn@latest add <component>` - Add shadcn/ui components
- `npm run registry:build` - Build and publish components to /public/r

## Architecture Overview

This is a React component library for Agentex built with Next.js 15, designed to provide UI components for AI agent interactions.

### Key Architectural Patterns

**State Management**: Uses Zustand stores with React Context pattern:

- `AgentexRoot` - Root level context for agents and tasks management
- `AgentexTask` - Task-specific context for message handling
- Store pattern: `use-{component}-store.ts` and `use-{component}-controller.ts`

**Component Distribution**: Uses shadcn/ui pattern for component distribution:

- `/registry` - Source code for publishing
- `registry.json` - Registry definition
- `/public/r` - Published component definitions (JSON)
- Components are built from `/registry` into `/public/r` as defined by `registry.json` using the script `npm run registry:build`
- Components can be installed in other projects via `npx shadcn@latest add http://localhost:3000/r/{component}.json`

**Agent Communication**: Supports two agent types:

- `agentic` - Event-based communication via `event/send` RPC
- `sync` - Streaming message communication via `message/send` RPC

### Folder Structure

```text
/app - Next.js App Router
  /dev - Local development only pages
/components - Private/WIP components + shadcn/ui base components
/entrypoints - Different single-page applications
/registry/agentex - Source code for published UI components
  /agentex-root - Root context components
  /agentex-task - Task context components
  <other components>
/public/r - Published component definitions
```

### Core Controllers

**AgentexRootController** (`registry/agentex/agentex-root/hooks/use-agentex-root-controller.ts:27`):

- `createTask()` - Creates new tasks and manages pending messages
- `popPendingMessageForTask()` - Handles pending message lifecycle with locking

**AgentexTaskController** (`registry/agentex/agentex-task/hooks/use-agentex-task-controller.ts:120`):

- `sendMessage()` - Handles different agent communication patterns (agentic vs sync)
- `isSendMessageEnabled` - Determines when message sending is allowed

## Development Setup

1. Start Agentex backend: `make dev` (in agentex/agentex directory)
2. Register ACP agent (see README.md for details)
3. Install dependencies: `npm install`
4. Start development: `npm run dev`

## Testing

Uses Jest with jsdom environment configured with Next.js integration. Currently no test files exist, but framework is ready.

- Test file patterns: `*.test.ts`, `*.spec.ts`, `__tests__/`
- Test environment: jsdom with Next.js configuration
- Run single test: `npm test -- --testNamePattern="test name"` or `npm test -- path/to/test.test.ts`

## Dependencies

Built on a React ecosystem:

- Next.js 15 with App Router and Turbopack
- React 19
- Radix UI primitives
- Tailwind CSS v4
- Zustand for state management
- React Hook Form + Zod for forms
- `agentex` npm package for agent communication
