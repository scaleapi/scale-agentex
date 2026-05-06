# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Public Repository

**This repository is public.** Everything that lands here — source code, comments, commit messages, file headers, runbooks, PR descriptions — is world-readable and indexed by search engines.

When making changes (especially commits, PR descriptions, and any operational docs), keep all of the following **out** of anything that gets pushed:

- Customer or account names (real or codename), and any identifying details about specific deployments, traffic patterns, or incidents tied to a customer.
- Internal Slack channels, threads, or permalinks (e.g. `scaleapi.slack.com/...`, `#some-internal-channel`).
- Internal ticket IDs and tracker URLs (Linear, Jira, etc.).
- Names or handles of individual employees, including in attribution like "per Alice's notes" or `Co-Authored-By` lines pointing at internal emails.
- Internal infrastructure references that aren't already documented publicly (internal hostnames, internal feature-flag system names, internal repo paths outside this one, etc.).
- Anything you wouldn't want a competitor or a journalist to read.

When describing motivation for a change, write generically: "on a sufficiently large table this exhausts the connection pool" rather than naming the specific table size, customer, or date. Describe the failure mode, not the incident.

When in doubt, ask before pushing — a redaction after the fact does not remove content from git history without a force-push that rewrites the branch.

## Repository Overview

Agentex is a comprehensive platform for building and deploying intelligent agents. This repository contains:

- **agentex/** - Backend services (FastAPI + Temporal workflows)
- **agentex-ui/** - Developer UI for interacting with agents

The platform integrates with the separate [agentex-python SDK](https://github.com/scaleapi/scale-agentex-python) for creating and running agents.

## Development Environment Setup

### Prerequisites

- Python 3.12+ (required for agentex-sdk)
- Docker and Docker Compose
- Node.js (for frontend)
- uv (Python package manager)

### Quick Start (Recommended)

One command does everything (auto-installs prerequisites if missing):

```bash
./dev.sh                    # Installs deps + starts backend + frontend
```

> Make sure Docker Desktop or Rancher Desktop is running first.

Other commands:
```bash
./dev.sh stop               # Stop all services
./dev.sh status             # Check service status
./dev.sh logs               # View all logs
./dev.sh restart            # Restart all services
```

**Then in a separate terminal - Agent Development:**
```bash
agentex init                # Create a new agent
cd your-agent-name/
uv venv && source .venv/bin/activate && uv sync
agentex agents run --manifest manifest.yaml
```

### Manual Setup (Alternative - 3 Terminals)

**Terminal 1 - Backend:**
```bash
cd agentex/
make dev                    # Starts Docker services and backend
```

**Terminal 2 - Frontend:**
```bash
cd agentex-ui/
npm install
npm run dev                 # Starts Next.js dev server
```

**Terminal 3 - Agent Development:**
```bash
agentex init                # Create a new agent
cd your-agent-name/
uv venv && source .venv/bin/activate && uv sync
agentex agents run --manifest manifest.yaml
```

### Backend Services (Docker Compose)

When running `make dev` in agentex/, the following services start:

- **Port 5003**: FastAPI backend server
- **Port 5432**: PostgreSQL (application database)
- **Port 5433**: PostgreSQL (Temporal database)
- **Port 6379**: Redis (streams and caching)
- **Port 27017**: MongoDB (document storage)
- **Port 7233**: Temporal server
- **Port 8080**: Temporal Web UI

All services are networked via `agentex-network` bridge network.

## Common Development Commands

### Backend (agentex/)

```bash
# Setup and installation
make install              # Install dependencies with uv
make install-dev          # Install with dev dependencies (includes pre-commit)
make clean                # Clean venv and lock files

# Development server
make dev                  # Start all Docker services
make dev-stop             # Stop Docker services
make dev-wipe             # Stop services and wipe volumes

# Database migrations
make migration NAME="description"  # Create new Alembic migration
make apply-migrations              # Apply pending migrations

# Testing
make test                                    # Run all tests
make test FILE=tests/unit/                   # Run unit tests
make test FILE=tests/unit/test_foo.py        # Run specific test file
make test NAME=crud                          # Run tests matching pattern
make test-unit                               # Unit tests shortcut
make test-integration                        # Integration tests shortcut
make test-cov                                # Run with coverage report
make test-docker-check                       # Verify Docker setup for tests

# Linting (ruff)
uv run ruff check src/                       # Check for lint errors
uv run ruff check src/ --fix                 # Auto-fix lint errors
uv run ruff format src/                      # Format code
uv run ruff check path/to/file.py            # Check specific file

# Documentation
make serve-docs           # Serve MkDocs on localhost:8001
make build-docs           # Build documentation

# Deployment
make docker-build         # Build production Docker image
```

### Frontend (agentex-ui/)

```bash
npm install               # Install npm dependencies
npm run dev               # Next.js dev server with Turbopack
npm run build             # Build production bundle
npm run typecheck         # TypeScript type checking
npm run lint              # Run ESLint
npm run format            # Run Prettier formatting
npm test                  # Run tests
```

### Agent Development (agentex-sdk)

```bash
# Always set this first
export ENVIRONMENT=development

# Agent management
agentex init                                      # Create new agent
agentex agents run --manifest manifest.yaml       # Run agent locally (dev)
agentex agents list                               # List all agents
agentex agents build --manifest manifest.yaml --push   # Build & push image
agentex agents deploy --manifest manifest.yaml         # Deploy to staging

# Package management (if using uv in agent)
agentex uv sync           # Sync dependencies
agentex uv add requests   # Add new dependency

# Other utilities
agentex tasks list        # View agent tasks
agentex secrets create    # Manage secrets
```

## Architecture

### Domain-Driven Design Structure

The backend (`agentex/src/`) follows a clean architecture with strict layer separation:

```
src/
├── api/                    # FastAPI routes, middleware, request/response schemas
│   ├── routes/             # API endpoints (agents, tasks, messages, spans, etc.)
│   ├── schemas/            # Pydantic request/response models
│   ├── authentication_middleware.py
│   └── app.py              # FastAPI application setup
├── domain/                 # Business logic (framework-agnostic)
│   ├── entities/           # Core domain models
│   ├── repositories/       # Data access interfaces
│   ├── services/           # Domain services
│   └── use_cases/          # Application use cases
├── adapters/               # External integrations
│   ├── crud_store/         # Database adapters (PostgreSQL, MongoDB)
│   ├── streams/            # Redis stream adapter
│   ├── authentication/     # Auth proxy adapter
│   └── authorization/      # Authz proxy adapter
├── config/                 # Configuration and dependencies
│   ├── dependencies.py     # Singleton for global dependencies (DB, Temporal, Redis)
│   └── mongodb_indexes.py
└── utils/                  # Shared utilities
```

**Key principles:**
- Domain layer has no dependencies on frameworks or adapters
- API layer handles HTTP concerns, delegates to use cases
- Adapters implement ports defined in domain layer
- Dependencies flow inward (API → Domain ← Adapters)

### Key Technologies

- **FastAPI**: Web framework with automatic OpenAPI docs at `/swagger` and `/api`
- **Temporal**: Workflow orchestration for long-running agent tasks
- **PostgreSQL**: Primary relational database (SQLAlchemy + Alembic migrations)
- **MongoDB**: Document storage for flexible schemas
- **Redis**: Streams for real-time communication and caching
- **Docker**: Containerization and local development

### Dependency Injection

Global dependencies are managed via a Singleton pattern in `src/config/dependencies.py`:

- `GlobalDependencies`: Singleton holding connections to Temporal, databases, Redis, etc.
- FastAPI dependencies use `Annotated` types (e.g., `DDatabaseAsyncReadWriteEngine`)
- Connection pools are configured with appropriate sizes for concurrency
- Startup/shutdown lifecycle managed in `app.py` lifespan context

### Testing Strategy

Tests are organized by type and use different strategies:

**Unit Tests** (`tests/unit/`):
- Fast, isolated tests using mocks
- Test domain logic, repositories, services
- Marked with `@pytest.mark.unit`

**Integration Tests** (`tests/integration/`):
- Test with real dependencies using testcontainers
- Postgres, Redis, MongoDB containers spun up automatically
- Test API endpoints end-to-end
- Marked with `@pytest.mark.integration`

**Test Runner** (`scripts/run_tests.py`):
- Automatically detects Docker environment
- Handles testcontainer setup
- Smart dependency installation
- Run via `make test` with various options

### Authentication & Authorization

- **Authentication**: Custom `AgentexAuthMiddleware` verifies requests via external auth service
- **Authorization**: Domain service (`authorization_service.py`) checks permissions
- **API Keys**: Agent-specific keys stored in PostgreSQL (`agent_api_keys` table)
- **Principal Context**: User/agent identity passed through request context

### Key Domain Concepts

- **Agents**: Autonomous entities that execute tasks, managed via ACP protocol
- **Tasks**: Work units with lifecycle states (pending → running → completed/failed)
- **Messages**: Communication between system and agents (stored in MongoDB)
- **Spans**: Execution traces for observability (OpenTelemetry-style)
- **Events**: Domain events for async communication
- **States**: Key-value state storage for agents
- **Deployment History**: Track agent deployment versions and changes

### Frontend Architecture (agentex-ui/)

- **Framework**: Next.js 15 with React 19 and App Router
- **Styling**: Tailwind CSS with Radix UI components
- **State**: React hooks and context
- **Forms**: React Hook Form with Zod validation
- **UI Components**: Custom components built on Radix primitives

## Important Notes

### Environment Variables

For local development, always set:
```bash
export ENVIRONMENT=development
```

Backend services read from:
- `DATABASE_URL`: PostgreSQL connection string
- `TEMPORAL_ADDRESS`: Temporal server address
- `REDIS_URL`: Redis connection string
- `MONGODB_URI`: MongoDB connection string
- `MONGODB_DATABASE_NAME`: MongoDB database name

Check `agentex/docker-compose.yml` for default values.

### Database Migrations

Always create migrations when changing models:
1. Modify SQLAlchemy models in `database/models/`
2. Run `make migration NAME="description"` from `agentex/`
3. Review generated migration in `database/migrations/versions/`
4. Apply with `make apply-migrations`

Migrations run automatically during `make dev` startup, and they also run on **pod startup in deployed environments**. This means a long-running migration blocks the application from coming up — the migration runner and the request-serving pod are the same process.

#### Migration safety on large or write-heavy tables

The default Alembic ergonomics (`op.add_column`, `op.create_index`, `op.create_foreign_key`, `op.execute("UPDATE ...")`) are fine on small tables but dangerous on large or hot ones. Combining several of them in a single revision has historically caused multi-row UPDATEs to hold `AccessExclusiveLock` for long enough to exhaust the application's connection pool. Treat the following as required reading whenever a migration touches a table that already has meaningful production volume.

**Rules of thumb:**

1. **One concern per revision.** A single migration should do one of: add a column, add a constraint, add an index, run a backfill. Never combine `add_column` + `UPDATE` backfill + `create_foreign_key` + `create_index` in one revision — each of those is fast in isolation and ruinous in combination on a large table.

2. **Never run a multi-million-row `UPDATE` in-band.** In-band backfills run inside Alembic's transaction, hold row locks, prevent autovacuum, and block pod startup. Use a separate, operator-driven runbook in `agentex/docs/runbooks/` that loops in batches with `COMMIT` between batches. See `spans-task-id-backfill.md` for the canonical pattern. The migration itself should add only the new column (nullable), and a follow-up migration should attach the FK/index after the backfill is done out-of-band.

3. **Add foreign keys with `NOT VALID`.** `op.create_foreign_key` issues `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` which scans the entire table under `AccessExclusiveLock`. On a large table this is the lock that takes the service down. Instead, write raw SQL with `NOT VALID` (skips the validation scan; FK still enforced on subsequent writes) and only run `VALIDATE CONSTRAINT` later if a fully validated state is actually needed (it is rarely needed; `VALIDATE CONSTRAINT` only takes `ShareUpdateExclusiveLock` so it is non-blocking but still scans the whole table).

4. **Build indexes with `CREATE INDEX CONCURRENTLY`.** `op.create_index` is non-concurrent and blocks writes for the duration of the build. On a large table use raw SQL (`CREATE INDEX CONCURRENTLY IF NOT EXISTS ...`) and wrap the whole migration in `op.get_context().autocommit_block()` — `CONCURRENTLY` cannot run inside a transaction.

5. **`autocommit_block()` requires per-migration transactions.** This repository's `env.py` already sets `transaction_per_migration=True`, but be aware: each migration is its own transaction, and `autocommit_block()` exits that transaction so individual statements (CREATE INDEX CONCURRENTLY, etc.) run with their own implicit transactions.

6. **Default timeouts apply.** `env.py` applies `lock_timeout = '3s'` and `statement_timeout = '30s'` per migration via `SET LOCAL` inside the transaction. This is intentional: it makes a runaway migration fail fast rather than block pod startup. Statements run via `autocommit_block()` deliberately bypass these timeouts (so legitimate long-but-non-blocking operations like `CREATE INDEX CONCURRENTLY` still work). If an in-transaction statement legitimately needs more headroom, override per-statement with `SET LOCAL`.

7. **Make migrations idempotent.** Use `IF NOT EXISTS` / `IF EXISTS` and catalog checks (`pg_constraint`, `pg_indexes`) so a migration is a no-op on environments where the operation has already run. This protects rollouts where some environments ran a previous (potentially broken) version of the migration and others did not.

8. **Test on representative data sizes.** A migration that completes in milliseconds against a near-empty dev table can take tens of minutes against a production table with tens of millions of rows. If you cannot test against a realistic dataset, write the migration as if you can't, and use the patterns above by default.

9. **Re-run, rollback, and forward-fix.** If a migration is rolled back in production, the `alembic_version` row reflects only what was committed. To recover from a partially-applied broken migration, reduce the broken revision to its safe minimum (idempotent column add, etc.) and add a follow-up migration that finalizes the rest under non-blocking operations. Do not silently rewrite history of a revision that has already been applied somewhere — always make the new behavior idempotent so it is safe on both already-applied and not-yet-applied environments.

If a planned migration touches a table you suspect is large in production, ask before merging and route the change through a runbook PR alongside the migration PR.

### Redis Port Conflicts

If you have local Redis running, it conflicts with Docker Redis on port 6379:
```bash
# macOS
brew services stop redis

# Linux
sudo systemctl stop redis-server
```

### Working with Temporal

- Access Temporal UI at http://localhost:8080
- Workflows are defined using temporalio Python SDK
- Task queues are used to route work to agents
- Workflow state persists across service restarts

### API Documentation

- Swagger UI: http://localhost:5003/swagger (interactive)
- ReDoc: http://localhost:5003/api (readable)
- OpenAPI spec: http://localhost:5003/openapi.json

## Adding New Features

### Adding a New API Endpoint

1. Define domain entity in `src/domain/entities/`
2. Create repository interface in `src/domain/repositories/`
3. Implement repository in `src/adapters/crud_store/`
4. Create use case in `src/domain/use_cases/`
5. Define request/response schemas in `src/api/schemas/`
6. Create route in `src/api/routes/`
7. Register router in `src/api/app.py`
8. Write tests in `tests/unit/` and `tests/integration/`

### Adding Database Tables

1. Create SQLAlchemy model in `database/models/`
2. Generate migration: `make migration NAME="add_table_name"`
3. Review and edit migration file if needed
4. Apply migration: `make apply-migrations`

### Adding MongoDB Collections

1. Define indexes in `src/config/mongodb_indexes.py`
2. Create entity in `src/domain/entities/`
3. Implement CRUD operations in `src/adapters/crud_store/adapter_mongodb.py`
4. Indexes are created automatically on startup

## Repository Structure

This repository contains two main components:
- **Backend**: `agentex/src/`, `agentex/database/`, `agentex/tests/`
- **Frontend**: `agentex-ui/`
