## UI: structure and module responsibilities

This section documents how the UI is organized and where to make common changes.

### `app/` (Next.js App Router)

- `app/layout.tsx`: root layout, global providers, global styles.
- `app/page.tsx`: main entry route that renders the application shell.
- `app/api/health/route.ts`: health endpoint for deployment checks.
- `app/loading.tsx`, `app/error.tsx`: route-level loading and error boundaries.

### `components/` (React components)

- `components/agentex-ui-root.tsx`: top-level UI composition; wires sidebars + primary content.
- `components/agents-list/*`: agent selection and agent badges.
- `components/task-sidebar/*`: list of tasks and task navigation.
- `components/primary-content/*`: chat view, home view, prompt input.
- `components/task-messages/*`: message rendering, streaming UI, tool-call display, markdown rendering.
- `components/traces-sidebar/*`: trace display panel.
- `components/task-header/*`: task header actions (theme toggle, trace inspection, etc.).
- `components/ui/*`: reusable UI primitives (buttons, forms, inputs, tooltip, toast, etc.).

### `hooks/` (data fetching and subscriptions)

Hooks encapsulate the data layer:

- React Query queries/mutations (agents, tasks, messages, spans)
- polling/streaming and websocket subscriptions (task updates)
- local storage state utilities and safe URL param parsing

This makes UI components mostly declarative and keeps network logic centralized.

### `lib/` (shared utilities)

Pure helpers for dates, JSON, and task transformations. This folder includes unit tests (`*.test.ts`) for utility logic.

### `providers/` (React context providers)

Providers are used for:

- query client wiring
- theme handling (light/dark mode)
- task/agent context state shared across the UI

