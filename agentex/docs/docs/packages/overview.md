## Repository packages

This repository contains two first-class packages:

- **`agentex/` (Agentex Backend)**: a FastAPI + Temporal service that stores agent/task data (Postgres + MongoDB), publishes realtime updates (Redis Streams + WebSockets), and exposes the HTTP API consumed by the UI and the Agentex SDK.
- **`agentex-ui/` (Agentex UI)**: a Next.js (App Router) developer UI for browsing agents, running tasks, chatting with agents, and inspecting execution traces.

This section documents how each package is structured, how to run it locally, where its public APIs live, and where to make changes for common feature work.

### How to read these docs

- **Backend package docs** focus on the *server’s* Python modules under `agentex/src/` (API layer, domain layer, adapters, config, and utilities).
- **UI package docs** focus on Next.js route handlers (`agentex-ui/app/`), React components (`agentex-ui/components/`), and data hooks (`agentex-ui/hooks/`).
- **Workspace docs** explain how the repo is composed (Python workspace + frontend package) and how CI and tooling are wired.

