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

#### Database Migration Safety

Schema migrations on hot tables (e.g. `spans`, anything with steady ingest) must preserve write availability. The migration runner sets `lock_timeout=3s`, `statement_timeout=30s`, and `idle_in_transaction_session_timeout=10s` by default (`agentex/database/migrations/alembic/env.py`), and a PR-time linter (`agentex/scripts/ci_tools/migration_lint.py`, run by pre-commit and CI) catches the patterns below before merge. Authors and reviewers — including Greptile — should treat these rules as the canonical "why" so the linter's output is actionable rather than mysterious.

Lead with schema-only changes, run data backfills out of band, and validate constraints in separate follow-up migrations.

| Anti-pattern | Why it is dangerous | Safer pattern | Linter rule |
|--------------|---------------------|---------------|-------------|
| Single unbatched `UPDATE` over a large table inside the migration transaction | Rewrites every touched row, creates proportional WAL/dead tuples, holds row locks until commit; rollback burns the same I/O again. | Move the backfill to an out-of-band script that chunks by id range or stable hash, sets `lock_timeout`, uses small batches, and sleeps between batches. | `no-timeout-overrides` (the runner's `statement_timeout` of 30s will also kill it) |
| `op.create_foreign_key(...)` without `postgresql_not_valid=True` | Validates every existing row immediately, taking `ShareRowExclusiveLock` on the child table while it scans. | Add the FK with `postgresql_not_valid=True`, then `op.execute("ALTER TABLE ... VALIDATE CONSTRAINT ...")` in a follow-up migration. | `prefer-robust-stmts` |
| Plain `op.create_index(...)` on a populated table | Takes `ShareLock` for the whole build and blocks `INSERT`/`UPDATE`/`DELETE`. | Use `postgresql_concurrently=True` inside `with op.get_context().autocommit_block():`. (Indexes on tables you `op.create_table` in the same migration are safe — the linter skips those automatically.) | `prefer-robust-stmts` |
| Mixing long DDL, validation, backfills, and concurrent index ops in one transaction | Locks stack together, and `CREATE INDEX CONCURRENTLY` cannot run inside Alembic's default per-migration transaction. | Split the rollout across small migrations, with explicit `autocommit_block` only around the concurrent index statement. | `transaction-nesting` |
| `op.create_unique_constraint(...)` directly on a hot table | Builds the supporting unique index while blocking writes. | Create a unique index concurrently, then attach it with `ADD CONSTRAINT ... USING INDEX` in a follow-up migration. | `disallowed-unique-constraint` |
| `op.add_column(... nullable=False, server_default=...)` on a populated table | Postgres rewrites the table to populate the value (volatile defaults always rewrite; constants are cheap on PG11+ but the linter is conservative). | Add the column nullable, backfill out of band, then `ALTER TABLE ... SET NOT NULL` in a follow-up migration. | `adding-required-field` |
| `SET lock_timeout`, `SET statement_timeout`, or `RESET` of either inside a migration file | Silently disables the runner's guardrails so the next slow migration takes a write outage. | Keep timeout policy in the runner; never override it per migration. | `no-timeout-overrides` |

Use this rollout shape for any change to a populated table:

1. **M1** — schema only: `op.add_column(... nullable=True)`, FKs with `postgresql_not_valid=True`, indexes via `postgresql_concurrently=True` inside `with op.get_context().autocommit_block():`.
2. **Out-of-band backfill** — a chunked script (id-range or hash-bucket pagination), with `lock_timeout` and a sleep between batches. Don't backfill inside a migration on a multi-million-row table — the runner's 30s `statement_timeout` will kill it, and the rollback burns all the I/O for nothing. Pattern: `agentex/docs/runbooks/spans-task-id-backfill.md`.
3. **M2** — `op.execute("ALTER TABLE ... VALIDATE CONSTRAINT ...")` for the FK, `op.alter_column(... nullable=False)` for the column, etc., once the backfill is verified.

#### Linter escape hatch

The linter is mechanical and occasionally over-cautious. To bypass an individual finding, add `# noqa: migration-lint` on the offending line and explain *why* in the PR description. A wholesale bypass (e.g. for a migration that genuinely requires a maintenance window) is signaled by applying the **`migration-unsafe-ack`** PR label — reviewers should treat that label as a contract that the PR description documents the maintenance window plan, the expected blast radius, and how the migration will be run. Do not use the label to ship faster; use it when the safe shape genuinely cannot apply.

Run the linter locally before pushing:

```bash
python agentex/scripts/ci_tools/migration_lint.py --base origin/main
```

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
