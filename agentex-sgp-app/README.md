# Agentex SGP App

A generic Agentex web client for SGP.

## Stack

- Next.js 15 (App Router), React 19, TypeScript
- Tailwind CSS v4, agentex-ui-kit, shadcn/ui
- State: Zustand stores + controller hooks
- Agentex SDK (`agentex`): API client + RPC helpers

## Prerequisites

- Node.js 20.x (match Docker base). Use npm (project ships `package-lock.json`).

## Quickstart (Local)

### 1. Env

```bash
cp example.env.development .env.development
# edit values as needed
```

Required public vars:

- `NEXT_PUBLIC_AGENTEX_API_BASE_URL` (e.g. `http://localhost:5003`)
- `NEXT_PUBLIC_SGP_APP_URL` (login redirect base; e.g. `https://egp.dashboard.scale.com`)

### 2. Install & run

```bash
make dev
# http://localhost:3000
```

## Scripts

- `make dev` — dev server (Turbopack)
- `make lint` — ESLint (Next config)
- `make typecheck` — TypeScript no-emit
- `make build` — production build
- `npm start` — start built app

## Architecture Map (what to read first)

- Entry points:
  - `app/page.tsx` → no-agent mode → `entrypoints/no-agent/*`
  - `app/agent/[agentName]/page.tsx` → single-agent mode → `entrypoints/single-agent/*`
- Bootstrap per mode:
  - `entrypoints/*/*-root.tsx` creates an `AgentexSDK`, fetches agents/tasks, and mounts a `Zustand` store via `AgentexRootStoreContext`.
- State:
  - `hooks/use-agentex-root-store.ts` — shared state that crosses task boundaries.
  - `hooks/use-agentex-root-controller.ts` — async functions that rely on shared state (e.g., `createTask`, pending-message orchestration).
  - `hooks/use-agentex-task-store.ts` — task-scoped store and selectors.
  - `hooks/use-agentex-task-controller.ts` — task-scoped functions (e.g., `sendMessage`).
- UI:
  - Reusable components under `components/agentex/*` and `components/ui/*`. Keep UI dump components stateless; put IO and branching in controllers.

## Conventions

- Prefer controller hooks for side effects and branching; components should be mostly presentational.
- Keep new public envs prefixed with `NEXT_PUBLIC_` and documented here.
- Co-locate mode-specific UI under `entrypoints/` rather than `app/` when possible.
