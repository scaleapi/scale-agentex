# Agentex UI

A modern web interface for building, testing, and monitoring intelligent agents. The Agentex UI provides a comprehensive developer experience for interacting with agents, managing tasks, and visualizing execution traces.

<img src="./docs/images/dashboard.png" alt="Agentex UI Dashboard" width="1280"/>

## Features

### Agent Management

- **Agent Discovery** - Browse and explore all available agents in your system
- **Agent Details** - View agent configurations, capabilities, and deployment status
- **Multi-Agent Support** - Work with multiple agents simultaneously

<img src="./docs/images/agents-list.gif" alt="Agents List" width="1280"/>

### Task Execution

- **Create Tasks** - Initialize agent tasks with custom parameters
- **Task History** - View complete task execution history with filtering by agent
- **Infinite Scroll** - Efficiently browse through long task lists

<img src="./docs/images/tasks-list.gif" alt="Tasks List" width="1280"/>

### Interactive Chat

- **Conversational Interface** - Send messages and interact with agents in real-time
- **Streaming Responses** - Live message streaming for sync agents
- **Message History** - Full conversation history with timestamps
- **Rich Content Support** - Display text, markdown, code, and structured data

<img src="./docs/images/chat-interface.gif" alt="Chat Interface" width="1280"/>

### Observability

- **Execution Traces** - View OpenTelemetry-style spans for task execution
- **Span Visualization** - Hierarchical view of execution flow
- **Performance Metrics** - Timing and duration information for each execution step
- **Error Tracking** - Detailed error information when tasks fail

<img src="./docs/images/execution-traces.gif" alt="Execution Traces" width="1280"/>

### Developer Experience

- **Real-time Updates** - Live task and message updates via WebSocket subscriptions
- **Optimistic UI** - Instant feedback with automatic cache updates
- **Error Handling** - User-friendly error messages with toast notifications
- **Dark Mode** - WCAG-compliant dark mode with proper contrast ratios

## Stack

- **Framework**: Next.js 15 (App Router), React 19, TypeScript
- **Styling**: Tailwind CSS v4, shadcn/ui components
- **State Management**: React Query for server state
- **Data Fetching**: Agentex SDK (`agentex`) for API client + RPC helpers
- **Real-time**: WebSocket subscriptions for live updates

## Prerequisites

- npm
- Running Agentex backend (see `../agentex/README.md`)

> **Windows Users**: Use PowerShell scripts (`build.ps1`) instead of Make commands throughout this guide.

## Getting Started from Scratch

### 1. Start the Backend

Before running the frontend, ensure the Agentex backend is running:

#### macOS/Linux

```bash
cd ../agentex
make dev
```

#### Windows (PowerShell)

```powershell
cd ../agentex
.\build.ps1 dev
```

This starts all required services (PostgreSQL, Redis, MongoDB, Temporal) and the FastAPI backend on port 5003.

### 2. Configure Environment Variables

Create your local environment file:

```bash
cd agentex-ui
cp example.env.development .env.development
```

Edit `.env.development` with your configuration:

```bash
# Backend API endpoint
NEXT_PUBLIC_AGENTEX_API_BASE_URL=http://localhost:5003
```

### 3. Install Dependencies

```bash
npm install
```

This installs all required packages including Next.js, React, Tailwind CSS, and the Agentex SDK.

### 4. Run the Development Server

#### macOS/Linux

```bash
npm run dev
# or using make
make dev
```

#### Windows (PowerShell)

```powershell
npm run dev
# or using PowerShell script
.\build.ps1 dev
```

The application will start on [http://localhost:3000](http://localhost:3000).

## Scripts

**Development:**

- `npm run dev` — Start dev server with Turbopack
- `npm run build` — Create production build
- `npm start` — Start production server

**Code Quality:**

- `npm run lint` — Run ESLint with zero warnings policy
- `npm run lint:fix` — Auto-fix linting issues
- `npm run typecheck` — TypeScript type checking
- `npm run format` — Format code with Prettier
- `npm run format:check` — Check formatting without writing

**Testing:**

- `npm test` — Run tests in watch mode
- `npm run test:run` — Run tests once (CI mode)
- `npm run test:ui` — Open Vitest UI for interactive testing
- `npm run test:coverage` — Generate coverage report

**Using PowerShell Scripts (Windows):**

For Windows users, the following PowerShell commands are available via `build.ps1`:

- `.\build.ps1 dev` — Start dev server (runs install and npm run dev)
- `.\build.ps1 install` — Install dependencies
- `.\build.ps1 typecheck` — TypeScript type checking
- `.\build.ps1 lint` — Run linting
- `.\build.ps1 build` — Build Docker image (includes typecheck and lint)
- `.\build.ps1 help` — Show all available commands

For Docker-related commands, see the Docker section in `build.ps1 help`.

## Architecture

### Code Structure

**Entry Point:**

- `app/page.tsx` → Main application entry → `app/home-view.tsx`

**State Management:**

- `hooks/use-agents.ts` - Fetches all agents via React Query
- `hooks/use-tasks.ts` - Task list with infinite scroll pagination
- `hooks/use-task-messages.ts` - Message fetching and sending with message streaming for sync agents
- `hooks/use-task-subscription.ts` - Real-time task updates via WebSocket for async agents
- `hooks/use-spans.ts` - Execution trace data

**Components:**

- `components/agentex/*` - Agentex-specific UI components (chat, task list, etc.)
- `components/ui/*` - Reusable UI primitives from shadcn/ui

## Testing

The project uses [Vitest](https://vitest.dev/) as the test runner with React Testing Library for component testing.

### Running Tests

```bash
# Watch mode (runs tests on file changes)
npm test

# Run once (useful for CI)
npm run test:run

# Interactive UI
npm run test:ui

# Generate coverage report
npm run test:coverage
```

### Test Configuration

The test suite is configured with:

- **Environment**: happy-dom (lightweight DOM simulation)
- **Globals**: Enabled for describe/it/expect without imports
- **Coverage**: v8 provider with text, JSON, and HTML reporters
- **Setup**: Path aliases configured to match Next.js (@/ → root, @/app, @/components, @/lib)

Coverage reports are generated in the `coverage/` directory and exclude config files, type definitions, and node_modules.

### Writing Tests

- Use Testing Library best practices for component tests
- Test files should be co-located with the code they test (e.g., `lib/utils.ts` → `lib/utils.test.ts`)
- Aim for high coverage on business logic and utility functions
