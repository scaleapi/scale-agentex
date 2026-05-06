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

#### Database migration safety

Default Alembic ergonomics — `op.add_column`, `op.create_index`, `op.create_foreign_key`, `op.execute("UPDATE ...")` — are fine on small tables and dangerous on large hot ones. The four anti-patterns below have all individually caused, or come close to causing, write outages. Read this section whenever a migration touches a table with meaningful production volume.

##### The four anti-patterns

1. **Single unbatched `UPDATE` over the whole table.** Postgres MVCC means every updated row becomes a rewrite plus a new tuple, so a multi-million-row `UPDATE` doubles live-plus-dead tuples on the table, generates proportional WAL, and holds row locks for the entire duration. If it fails or is killed, the whole transaction rolls back and burns all that I/O for nothing. **Don't backfill in a migration.** Chunk by id range or hash in an out-of-band script and run the schema-only parts in the migration.

2. **`op.create_foreign_key` (validating).** Default Alembic FK creation issues `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` which takes `ShareRowExclusiveLock` on the referencing table (and `AccessShare` on the referenced table) while it full-scans every row to prove the FK holds. **Two-step it:** add with `NOT VALID` first (cheap, metadata only), then `ALTER TABLE ... VALIDATE CONSTRAINT` in a follow-up migration (`ShareUpdateExclusiveLock`, scan-only, does not block writes). In Alembic: `op.create_foreign_key(..., postgresql_not_valid=True)` or write the raw `ALTER TABLE` with `NOT VALID`.

3. **`op.create_index` without `CONCURRENTLY`.** Plain `CREATE INDEX` takes a `ShareLock` on the table for the entire build, blocking every `INSERT` / `UPDATE` / `DELETE`. On a hot ingest table that's a write outage. Use `CREATE INDEX CONCURRENTLY` — which means the migration must run outside a transaction. In Alembic: `with op.get_context().autocommit_block(): op.execute("CREATE INDEX CONCURRENTLY ...")`.

4. **One transaction wrapping all of the above.** Alembic's default is one transaction per migration. With anti-patterns 1–3 stacked in a single revision the locks compound and every writer queues behind them. Use `transaction_per_migration=True` (already set in `env.py`) and `autocommit_block()` for `CONCURRENTLY` operations so the migration cannot accidentally hold compound locks.

##### The correct shape: split into M1, out-of-band backfill, M2

For any migration that adds a backfilled column with an FK and an index on a large table, ship three things in order:

| Step | What | Why |
|---|---|---|
| **M1 (Alembic)** | `ADD COLUMN` (nullable) + `ADD CONSTRAINT ... NOT VALID` + `CREATE INDEX CONCURRENTLY` (in `autocommit_block()`) | Schema-only, all metadata-cheap or non-blocking. Each operation is idempotent (`IF NOT EXISTS` / `pg_constraint` guard) so the migration is safe to re-run on environments that already ran a previous (broken) version. |
| **Out-of-band runbook** | Chunked backfill script with `lock_timeout`, small batches, `COMMIT` between batches, `pg_sleep` between batches | Operator-driven; runs during a low-traffic window, can be cancelled cleanly, doesn't block pod startup. Pattern: `agentex/docs/runbooks/spans-task-id-backfill.md`. |
| **M2 (Alembic)** | `ALTER TABLE ... VALIDATE CONSTRAINT` (only if a fully validated FK state is actually needed) | Runs after the backfill so the scan finds no violations. `ShareUpdateExclusiveLock` is non-blocking against reads/writes but still scans the table — usually optional. |

The application should also tolerate the partially-backfilled state at read time (e.g. ORing the new column against the legacy column where they overlap) so deployment of M1 is decoupled from the backfill's completion.

##### Default runtime guardrails

`env.py` applies three timeouts per migration via `SET LOCAL` inside the transaction:

- `lock_timeout = '3s'` — fail fast if the migration's DDL would queue behind active writers.
- `statement_timeout = '30s'` — cap per-statement runtime so a runaway query aborts cleanly.
- `idle_in_transaction_session_timeout = '10s'` — kill a stalled transaction so it can't hold locks indefinitely.

Statements run via `autocommit_block()` are outside the transaction and bypass these timeouts deliberately — that's the right behavior for `CREATE INDEX CONCURRENTLY` and similar long-but-non-blocking operations.

##### Escape hatch: `migration-unsafe-ack`

A migration that genuinely needs to override these guardrails (a pre-approved maintenance-window operation, for example) must:

1. Open the migration file with a top-of-file directive comment:

   ```python
   # migration-unsafe-ack: <one-line reason>
   ```

2. Add the `migration-unsafe-ack` label on the PR.

The directive is what lets a migration include `SET lock_timeout`, `SET statement_timeout`, `SET idle_in_transaction_session_timeout`, or `RESET` of any of those. The PR label is what tells the reviewer the override is intentional.

Use the escape hatch for "this needs a maintenance window with traffic shifted away" — not for "I want to ship faster." If you find yourself reaching for it, the answer is almost always to split the migration into the M1 / out-of-band / M2 shape above.

##### Anti-pattern → linter rule reference

A migration linter is planned (see SGP-5785) and will enforce these rules at PR time. The mapping below is what the linter will catch — and what reviewers should look for in the meantime:

| Anti-pattern | Linter rule (squawk or equivalent) |
|---|---|
| `CREATE INDEX` without `CONCURRENTLY` | `prefer-robust-stmts` |
| `ADD CONSTRAINT FOREIGN KEY` without `NOT VALID` | `prefer-robust-stmts` |
| `ADD CONSTRAINT ... UNIQUE` (use `CREATE UNIQUE INDEX CONCURRENTLY` + `ADD CONSTRAINT ... USING INDEX` instead) | `disallowed-unique-constraint` |
| `ADD COLUMN ... NOT NULL` with a volatile default | `adding-required-field` |
| Mixing `CONCURRENTLY` ops with same-transaction DDL | `transaction-nesting` |
| `SET lock_timeout` / `SET statement_timeout` / `SET idle_in_transaction_session_timeout` / `RESET` of any | custom rule (forbidden unless `# migration-unsafe-ack: ...` directive present) |

##### Other rules

- **Make migrations idempotent.** Use `IF NOT EXISTS` / `IF EXISTS` and catalog checks (`pg_constraint`, `pg_indexes`) so a migration is a no-op on environments where the operation has already run.
- **Test on representative data sizes.** A migration that finishes instantly against an empty dev table can take tens of minutes against a multi-million-row prod table.
- **Forward-fix, don't quietly rewrite.** If a migration ships broken to any environment, reduce the broken revision to its safe minimum (idempotent column add) and add a follow-up migration that finalizes the rest under non-blocking operations. Don't rewrite a revision's body in a way that would skip work on environments where the original ran successfully.

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
