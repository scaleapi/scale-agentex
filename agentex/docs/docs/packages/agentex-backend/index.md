## `agentex/` (Agentex Backend)

The backend is a FastAPI service that provides the Agentex HTTP API, orchestrates long-running work with Temporal, and persists agent/task state across:

- **PostgreSQL**: relational data (agents, tasks metadata, API keys, deployment history).
- **MongoDB**: flexible documents (task messages and related content).
- **Redis**: streams and caching for realtime updates and subscriptions.

The codebase is organized using a clean-architecture / ports-and-adapters style:

- **API layer (`src/api/`)**: HTTP concerns (routes, schemas, middleware). Delegates to use cases.
- **Domain layer (`src/domain/`)**: business logic, entities, repository interfaces, services, use cases.
- **Adapters (`src/adapters/`)**: implementations of ports for databases, Redis streams, Temporal, HTTP clients, and auth proxies.
- **Config (`src/config/`)**: environment variables, global dependency wiring, startup/shutdown initialization.
- **Temporal (`src/temporal/`)**: workers, workflows, and activities used for backend background jobs.
- **Utilities (`src/utils/`)**: shared helpers (ids, pagination, logging, timestamp, http clients).

### Entry points

- **FastAPI app**: `src/api/app.py`
- **HTTP routes**: `src/api/routes/` (mounted by the app)
- **Temporal worker**: `src/temporal/run_worker.py`

### Local development

From `agentex/`:

```bash
uv sync --group dev
docker compose up --build
```

Useful commands (see `agentex/Makefile` for the authoritative list):

```bash
make dev
make test
make serve-docs
```

### Public surface area

The backend’s public interfaces are:

- **HTTP API** served by FastAPI (see `src/api/routes/*` and the OpenAPI docs at `/swagger`).
- **WebSocket / streaming updates** used by the UI for realtime task/message updates.
- **Temporal workflows and activities** used for durable background execution.

Internal modules (domain + adapters) are meant to be imported by the server only; downstream clients should use the HTTP API or the Agentex SDK.

