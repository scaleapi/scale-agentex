## Backend: configuration & dependency wiring (`src/config/`)

The backend uses explicit dependency wiring to keep framework concerns (FastAPI) and infrastructure concerns (databases, Redis, Temporal) separated from domain logic.

### What lives here

- **Environment variables**: `src/config/environment_variables.py`
  - Defines and validates settings that control service behavior (DB URLs, Temporal address, Redis URL, Mongo settings, auth proxy settings, etc.).
  - Prefer adding new settings here and reading them via a typed settings object rather than calling `os.getenv` throughout the codebase.
- **Global dependencies**: `src/config/dependencies.py`
  - Creates long-lived clients/engines (SQLAlchemy engine, Mongo client, Redis client, Temporal client).
  - Exposes dependency providers for FastAPI routes (e.g., “read/write DB engine”).
  - Manages startup/shutdown lifecycle (connect, health checks, close pools).
- **MongoDB indexes**: `src/config/mongodb_indexes.py`
  - Central place to define required indexes for MongoDB collections.
  - Index creation is typically performed during startup.

### Common environment variables

The backend reads most configuration via environment variables. Common ones include:

- **`ENVIRONMENT`**: `development`, `staging`, or `production`.
- **`DATABASE_URL`**: Postgres connection string.
- **`MONGODB_URI` / `MONGODB_DATABASE_NAME`**: Mongo connection and database name.
- **`REDIS_URL`**: Redis connection string (required for realtime streaming/subscriptions).
- **`TEMPORAL_ADDRESS` / `TEMPORAL_NAMESPACE`**: Temporal server configuration.
- **`AGENTEX_AUTH_URL`**: authentication proxy URL (if enabled).
- **`ALLOWED_ORIGINS`**: CORS configuration.

### How dependencies are used

- API routes request dependencies using FastAPI’s dependency injection.
- Use cases and services accept repositories/ports (interfaces) or already-wired adapters.
- Adapters own concrete client objects (sqlalchemy sessions/engines, pymongo clients, redis clients, temporal clients).

### Adding a new dependency

When adding a new infrastructure dependency:

1. Add configuration in `environment_variables.py`.
2. Create the client/engine in `dependencies.py`.
3. Expose it through a FastAPI dependency provider if routes need it.
4. Ensure you close it on shutdown (connection pools, aio clients).
5. Add or update health checks (if the service is required for startup).

