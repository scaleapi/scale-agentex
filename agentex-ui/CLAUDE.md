# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Local Development

- `make dev` — Start development server with Turbopack (recommended)
- `make install` — Install npm dependencies

### Quality Checks

- `make typecheck` — Run TypeScript type checking (npm run typecheck)
- `make lint` — Run ESLint with Next.js config (npm run lint)
- **Always run both typecheck and lint before committing changes**

### Build & Deploy

- `make build` — Production build (runs typecheck + lint first)
- `npm start` — Start built production app
- `make build-and-run` — Build Docker image and run locally

## Architecture Overview

This is a Next.js 15 app with App Router that provides a web client for the Agentex platform. The app supports two main modes:

### Entry Points & Routing

- **No-agent mode**: `app/page.tsx` → `entrypoints/no-agent/*` (agent selection)
- **Single-agent mode**: `app/agent/[agentName]/page.tsx` → `entrypoints/single-agent/*` (task management)

### State Management Architecture

The app uses Zustand stores with a dual-layer state management pattern:

#### Root-level State (`hooks/use-agentex-root-store.ts`)

- Cross-task shared state (agents, tasks, message cache)
- Managed via `AgentexRootStoreContext`
- Bootstrapped in `*-root.tsx` components with AgentexSDK instance

#### Task-level State (`hooks/use-agentex-task-store.ts`)

- Task-scoped state and message handling
- Isolated per task but syncs previews to root store

#### Controller Pattern (`hooks/use-agentex-root-controller.ts`, `hooks/use-agentex-task-controller.ts`)

- Async operations and side effects separated from stores
- `createTask`, `sendMessage`, pending message orchestration
- Controllers consume stores but handle all IO and branching logic

### Pending Message System

Complex synchronization mechanism in `lib/pending-message.ts`:

- `PendingMessageLock` ensures exactly one initial message per task
- Prevents race conditions when task creation + first message happen simultaneously
- Used in create-task workflows to stage initial user input

### Component Organization

- `components/agentex/*` — Domain-specific reusable components
- `components/ui/*` — Generic UI components (shadcn/ui based) - only used by shadcn, do not add components to this directory unless they are shadcn
- `entrypoints/*/` — Mode-specific page components and views
- Follow pattern: **components should be presentational, controllers handle side effects**

## Tech Stack Details

- Next.js 15 (App Router) + React 19 + TypeScript
- Tailwind CSS v4 + shadcn/ui components
- Agentex SDK for API communication + RPC helpers
- State: Zustand stores + custom controller hooks pattern

## Environment Setup

Required environment variables:

- `NEXT_PUBLIC_AGENTEX_API_BASE_URL` — Backend API URL
- `NEXT_PUBLIC_SGP_APP_URL` — Login redirect base URL

Copy `example.env.development` to `.env.local` and configure values.

## Testing

No automated testing framework is currently configured. When adding tests, check the codebase for existing test patterns and follow them.

## Conventions

- Keep components stateless and presentational
- Use controller hooks for side effects, API calls, and state mutations
- All public env vars must be prefixed with `NEXT_PUBLIC_`
- Co-locate mode-specific UI under `entrypoints/` rather than `app/`
- New features should follow the existing controller + store + component pattern
