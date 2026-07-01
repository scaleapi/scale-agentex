## Backend: API layer (`src/api/`)

The API layer translates HTTP requests into domain use-case calls and translates domain objects back into HTTP responses.

### What lives here

- **App wiring**: `src/api/app.py`
  - Creates the FastAPI application.
  - Registers middleware.
  - Includes routers from `src/api/routes/`.
  - Handles lifespan startup/shutdown hooks (dependency initialization).
- **Routes**: `src/api/routes/*.py`
  - Resource-oriented routers (agents, tasks, messages, spans, state, events, schedules, etc.).
  - Request validation and response shaping via schema models.
  - Delegation to use cases in `src/domain/use_cases/`.
- **Schemas**: `src/api/schemas/*.py`
  - Pydantic models for request/response payloads.
  - Versioning/backwards-compatibility (when needed) should be handled here instead of leaking into domain code.
- **Middleware**:
  - `src/api/authentication_middleware.py`: request authentication and principal context population.
  - `src/api/RequestLoggingMiddleware.py`: request/response logging.
  - `src/api/middleware_utils.py`: shared middleware helpers.
- **Auth cache**: `src/api/authentication_cache.py`
  - Caches authentication lookups (used by auth middleware and/or adapters).

### Routers (HTTP resources)

The backend registers these routers in `src/api/app.py`:

- **`agents.py`**: agent CRUD/registration, ACP-related agent metadata.
- **`tasks.py`**: task creation, listing, and lifecycle operations.
- **`messages.py`**: task message creation and retrieval (including streaming patterns).
- **`spans.py`**: execution trace spans (OpenTelemetry-style).
- **`states.py`**: agent/task state storage (key/value style state).
- **`events.py`**: event ingestion and retrieval for agent/task workflows.
- **`agent_task_tracker.py`**: “agent task tracker” endpoints used to coordinate long-running/background work.
- **`agent_api_keys.py`**: agent API key management.
- **`deployment_history.py`**: deployment/version history for agents.
- **`schedules.py`**: schedules for recurring or deferred task execution.
- **`health.py`**: health and readiness endpoints.

### Dependency flow

API routes should depend only on:

- **Domain use cases** (`src/domain/use_cases/*`), and
- **FastAPI dependencies** (injected handles to adapters via `src/config/dependencies.py`)

Routes should *not* directly depend on concrete adapter implementations (Postgres/Mongo/Redis/etc.). That keeps the domain and test layers isolated.

### Adding a new endpoint (pattern)

When adding a new endpoint, prefer this sequence:

1. Define or extend domain entities in `src/domain/entities/`.
2. Add/extend repository interface(s) in `src/domain/repositories/`.
3. Implement the repository in `src/adapters/`.
4. Add a use case in `src/domain/use_cases/`.
5. Add request/response models in `src/api/schemas/`.
6. Add a router in `src/api/routes/` and include it in `src/api/app.py`.
7. Add unit/integration tests in `tests/unit/` and `tests/integration/`.

