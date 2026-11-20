## Backend: adapters (`src/adapters/`)

Adapters are the concrete implementations of domain “ports” (repository interfaces, external services, and infrastructure clients). Adapters are where the backend talks to Postgres, MongoDB, Redis, Temporal, and external auth services.

### Adapter families

#### CRUD store (`src/adapters/crud_store/`)

- **Purpose**: persistence implementation across SQL (Postgres) and documents (MongoDB).
- **Key files**:
  - `adapter_postgres.py`: SQLAlchemy-based implementation for relational entities.
  - `adapter_mongodb.py`: MongoDB implementation for message-like collections.
  - `port.py`: port/interface definitions used by higher layers.
  - `exceptions.py`: adapter-specific errors.

#### Streams (`src/adapters/streams/`)

- **Purpose**: realtime updates and pub/sub over Redis Streams.
- **Key files**:
  - `adapter_redis.py`: Redis client implementation.
  - `port.py`: stream adapter interface.

#### Temporal (`src/adapters/temporal/`)

- **Purpose**: access to Temporal as a workflow engine.
- **Key files**:
  - `adapter_temporal.py`: Temporal client wrapper.
  - `client_factory.py`: consistent client construction.
  - `port.py`: Temporal adapter interface.
  - `exceptions.py`: Temporal adapter errors.

#### HTTP (`src/adapters/http/`)

- **Purpose**: outbound HTTP calls (e.g., to auth proxies or other services).
- **Key files**:
  - `adapter_httpx.py`: httpx-based client adapter.
  - `port.py`: HTTP adapter interface.

#### Authentication & authorization (`src/adapters/authentication/`, `src/adapters/authorization/`)

- **Purpose**: integration with external identity/permissions systems.
- **Key files**:
  - `adapter_agentex_authn_proxy.py`: authentication proxy implementation.
  - `adapter_agentex_authz_proxy.py`: authorization proxy implementation.
  - `port.py`: interface definitions.
  - `exceptions.py`: adapter errors.

### Adding a new adapter

When introducing a new integration:

1. Define an interface in `src/domain/repositories/` or an adapter `port.py` (depending on whether it’s persistence or infrastructure).
2. Implement the interface under `src/adapters/<family>/`.
3. Wire it into dependency injection in `src/config/dependencies.py`.
4. Add tests:
   - unit tests for domain behavior using mocks
   - integration tests for real dependency behavior (when practical)

