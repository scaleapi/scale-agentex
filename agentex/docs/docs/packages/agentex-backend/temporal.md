## Backend: Temporal (`src/temporal/`)

Temporal is used to run durable background workflows (long-running, retriable, stateful processes). The backend typically uses Temporal for:

- background health checks
- durable execution patterns for agent task orchestration (when using a Temporal-based ACP)

### What lives here

- **Workflows**: `src/temporal/workflows/`
  - Workflow definitions (stateful orchestration).
- **Activities**: `src/temporal/activities/`
  - Side-effecting operations invoked by workflows (I/O, network calls, database operations).
- **Worker runner**: `src/temporal/run_worker.py`
  - Starts a worker process to poll a task queue and execute workflows/activities.
- **Workflow runner(s)**: `src/temporal/run_healthcheck_workflow.py`
  - Convenience entrypoints for running specific workflows.

### Design guidelines

- Workflows should be deterministic; keep I/O in activities.
- Prefer passing small, serializable payloads between workflow/activity boundaries.
- Keep activity interfaces stable; treat them similarly to internal APIs.

### Operating locally

Temporal is provided by Docker Compose when running `make dev` in `agentex/`.

