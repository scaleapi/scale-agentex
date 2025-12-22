## Backend: domain layer (`src/domain/`)

The domain layer contains the application’s core business logic. It is designed to be framework-agnostic: no FastAPI objects, no database drivers, no Redis/Temporal clients.

### What lives here

- **Entities (`src/domain/entities/`)**
  - Domain objects that represent the system’s state and payloads: agents, tasks, messages, spans, events, states, schedules, and supporting types.
  - These are the types your use cases should speak.
- **Repository interfaces (`src/domain/repositories/`)**
  - Abstract “ports” for persistence and external I/O (agents repository, task repository, message repository, span repository, etc.).
  - Adapters implement these interfaces.
- **Services (`src/domain/services/`)**
  - Reusable domain logic that doesn’t belong to a single use case (authorization, task/message orchestration, scheduling rules, ACP interactions).
- **Use cases (`src/domain/use_cases/`)**
  - Application operations invoked by the API layer.
  - Use cases coordinate repository calls, enforce invariants, and return domain entities.
- **Exceptions (`src/domain/exceptions.py`)**
  - Domain-level errors that can be mapped to HTTP responses in the API layer.

### Typical call flow

1. A route handler validates the incoming request via `src/api/schemas/*`.
2. The route invokes a use case in `src/domain/use_cases/*`.
3. The use case calls repository interfaces and/or services.
4. Adapter implementations satisfy repository calls and return domain entities.
5. The route serializes the domain result into a response schema.

### Where to put new logic

- **New business rule** shared across multiple operations: add a domain service.
- **New operation** that changes user-visible behavior: create a new use case (or extend an existing one).
- **New persistence need**: extend a repository interface and update the adapter(s).

