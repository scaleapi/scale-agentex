# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Agentex is a comprehensive platform for building and deploying intelligent agents. This repository contains:

- **agentex/** - Backend services (FastAPI + Temporal workflows)
- **agentex-sgp-app/** - Developer UI for interacting with agents

The platform integrates with the separate [agentex-python SDK](https://github.com/scaleapi/scale-agentex-python) for creating and running agents.

## Development Environment Setup

### Prerequisites

- Python 3.12+ (required for agentex-sdk)
- Docker and Docker Compose
- Node.js (for frontend)
- uv (Python package manager)

### Quick Start (3-Terminal Setup)

**Terminal 1 - Backend:**
```bash
cd agentex/
make dev                    # Starts Docker services and backend
```

**Terminal 2 - Frontend:**
```bash
cd agentex-sgp-app/
npm install
npm run dev                 # Starts Next.js dev server
```

**Terminal 3 - Agent Development:**
```bash
export ENVIRONMENT=development
agentex init                # Create a new agent
cd your-agent-name/
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

# Documentation
make serve-docs           # Serve MkDocs on localhost:8001
make build-docs           # Build documentation

# Deployment
make docker-build         # Build production Docker image
```

### Frontend (agentex-sgp-app/)

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

### Frontend Architecture (agentex-sgp-app/)

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

Migrations run automatically during `make dev` startup.

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
- **Frontend**: `agentex-sgp-app/`
