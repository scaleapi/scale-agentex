# Internal Architecture

This document describes the internal code architecture of the Agentex backend. For a high-level conceptual overview, see [Agentex Overview](../getting_started/agentex_overview.md).

## High-Level Architecture (Hexagonal/Clean Architecture)

The codebase follows a **Hexagonal Architecture** (also known as Ports & Adapters) with clear separation between layers:

```mermaid
graph TB
    subgraph External["External Clients"]
        UI[Agentex UI]
        SDK[Python SDK]
        Agents[Agent Containers]
    end

    subgraph API["API Layer (src/api)"]
        direction TB
        HCI[HealthCheckInterceptor<br/>ASGI Level]
        CORS[CORSMiddleware]
        Auth[AgentexAuthMiddleware]
        ReqLog[RequestLoggingMiddleware]
        Routes[Route Handlers<br/>LoggedAPIRoute]
    end

    subgraph Domain["Domain Layer (src/domain)"]
        direction TB
        UC[Use Cases]
        SVC[Services]
        ENT[Entities]
        REPO[Repository Interfaces]
    end

    subgraph Adapters["Adapters Layer (src/adapters)"]
        direction TB
        PG[PostgresCRUDRepository]
        MONGO[MongoDBCRUDRepository]
        REDIS[RedisStreamRepository]
        TEMP[TemporalAdapter]
        HTTP[HttpxGateway]
        AUTHN[AuthenticationProxy]
        AUTHZ[AuthorizationProxy]
    end

    subgraph Infrastructure["Infrastructure"]
        PostgreSQL[(PostgreSQL)]
        MongoDB[(MongoDB)]
        RedisDB[(Redis)]
        Temporal[Temporal Server]
        AuthSvc[Auth Service]
    end

    UI --> HCI
    SDK --> HCI
    Agents --> HCI

    HCI --> CORS --> Auth --> ReqLog --> Routes
    Routes --> UC
    UC --> SVC
    SVC --> REPO

    REPO -.-> PG
    REPO -.-> MONGO
    REPO -.-> REDIS
    SVC -.-> TEMP
    SVC -.-> HTTP
    Auth -.-> AUTHN
    UC -.-> AUTHZ

    PG --> PostgreSQL
    MONGO --> MongoDB
    REDIS --> RedisDB
    TEMP --> Temporal
    HTTP --> Agents
    AUTHN --> AuthSvc
    AUTHZ --> AuthSvc
```

---

## Request Flow

Every HTTP request follows this path through the system:

```mermaid
sequenceDiagram
    participant C as Client
    participant HCI as HealthCheckInterceptor
    participant MW as Middleware Stack
    participant R as Route Handler
    participant UC as Use Case
    participant SVC as Service
    participant DB as Database

    C->>HCI: HTTP Request

    alt Health Check Path
        HCI-->>C: 200 OK (fast path)
    else Regular Request
        HCI->>MW: Forward
        MW->>MW: CORS → Auth → RequestLogging
        MW->>R: Authenticated Request
        R->>UC: Dependency Injection
        UC->>SVC: Business Logic
        SVC->>DB: Data Access
        DB-->>SVC: Result
        SVC-->>UC: Domain Entity
        UC-->>R: Response Schema
        R-->>C: JSON Response
    end
```

---

## Domain Layer Structure

The domain layer follows a layered pattern with clear responsibilities:

- **Use Cases**: Application-level orchestration, convert between API schemas and domain entities
- **Services**: Business logic, coordinate between repositories
- **Repositories**: Data access interfaces (implemented by adapters)

```mermaid
graph LR
    subgraph UseCases["Use Cases"]
        AgentsUC[AgentsUseCase]
        TasksUC[TasksUseCase]
        MessagesUC[MessagesUseCase]
        SpansUC[SpanUseCase]
        SchedulesUC[SchedulesUseCase]
        ACPUC[AgentsACPUseCase]
    end

    subgraph Services["Services"]
        TaskSVC[AgentTaskService]
        MsgSVC[TaskMessageService]
        ACPSVC[AgentACPService]
        AuthzSVC[AuthorizationService]
        SchedSVC[ScheduleService]
    end

    subgraph Repositories["Repositories"]
        AgentRepo[AgentRepository]
        TaskRepo[TaskRepository]
        MsgRepo[TaskMessageRepository]
        SpanRepo[SpanRepository]
        EventRepo[EventRepository]
    end

    AgentsUC --> AgentRepo
    TasksUC --> TaskSVC
    MessagesUC --> MsgSVC
    SpansUC --> SpanRepo
    SchedulesUC --> SchedSVC
    ACPUC --> TaskSVC
    ACPUC --> ACPSVC
    ACPUC --> AuthzSVC

    TaskSVC --> TaskRepo
    TaskSVC --> EventRepo
    TaskSVC --> ACPSVC
    MsgSVC --> MsgRepo
    ACPSVC --> AgentRepo
```

---

## Data Storage Split

Data is split across different storage backends based on access patterns:

```mermaid
graph TB
    subgraph PostgreSQL["PostgreSQL (Relational)"]
        Agents[agents]
        Tasks[tasks]
        Events[events]
        Spans[spans]
        APIKeys[agent_api_keys]
        Deployments[deployment_history]
        Trackers[agent_task_trackers]
    end

    subgraph MongoDB["MongoDB (Documents)"]
        Messages[messages<br/>Flexible schema]
        States[task_states<br/>Key-value pairs]
    end

    subgraph Redis["Redis (Streams)"]
        TaskEvents[task_events_*<br/>Real-time streaming]
    end

    subgraph Temporal["Temporal (Workflows)"]
        Schedules[Recurring schedules]
        Workflows[Long-running workflows]
    end
```

| Storage | Use Case | Why |
|---------|----------|-----|
| **PostgreSQL** | Agents, Tasks, Spans, Events | Relational integrity, ACID transactions, complex queries |
| **MongoDB** | Messages, States | Flexible schema for varied content types, document-oriented |
| **Redis** | Task event streams | Real-time pub/sub, SSE streaming to clients |
| **Temporal** | Schedules, Workflows | Durable workflow orchestration, reliable scheduling |

---

## API Routes Overview

All routes are organized in `src/api/routes/`:

```mermaid
graph LR
    subgraph Routes["API Routes (10 files, 26 GET endpoints)"]
        A["/agents"] --> A1[CRUD + Register + RPC]
        T["/tasks"] --> T1[CRUD + Streaming]
        M["/messages"] --> M1[CRUD + Pagination]
        S["/spans"] --> S1[CRUD]
        ST["/states"] --> ST1[CRUD]
        E["/events"] --> E1[CRUD]
        K["/agent_api_keys"] --> K1[CRUD]
        D["/deployment-history"] --> D1[List + Get]
        TR["/tracker"] --> TR1[Get + Update]
        SC["/agents/{id}/schedules"] --> SC1[CRUD + Pause/Trigger]
    end
```

---

## Middleware Stack

Middleware executes in this order (first to last):

```mermaid
graph TB
    REQ[Incoming Request] --> HCI

    subgraph Stack["Middleware Stack"]
        HCI[1. HealthCheckInterceptor<br/>ASGI Level - Fast Path]
        CORS[2. CORSMiddleware<br/>Handle CORS headers]
        AUTH[3. AgentexAuthMiddleware<br/>Verify identity]
        LOG[4. RequestLoggingMiddleware<br/>Generate request ID]
        ROUTE[5. LoggedAPIRoute<br/>Log req/res + handle]
    end

    HCI -->|Non-health paths| CORS
    CORS --> AUTH
    AUTH --> LOG
    LOG --> ROUTE
    ROUTE --> RESP[Response]

    HCI -->|/healthz, /healthcheck| FAST[200 OK<br/>Sub-millisecond]
```

| Middleware | Purpose |
|------------|---------|
| **HealthCheckInterceptor** | ASGI-level fast path for Kubernetes probes |
| **CORSMiddleware** | Handle cross-origin requests |
| **AgentexAuthMiddleware** | Verify agent identity or auth tokens |
| **RequestLoggingMiddleware** | Generate request ID for log correlation |
| **LoggedAPIRoute** | Log requests/responses, handle streaming |

---

## Key Files Reference

| Layer | Directory | Key Files |
|-------|-----------|-----------|
| **API** | `src/api/` | `app.py`, `logged_api_route.py`, `authentication_middleware.py` |
| **Routes** | `src/api/routes/` | `agents.py`, `tasks.py`, `messages.py`, `spans.py`, etc. |
| **Domain** | `src/domain/` | `entities/`, `use_cases/`, `services/`, `repositories/` |
| **Adapters** | `src/adapters/` | `crud_store/`, `temporal/`, `streams/`, `http/` |
| **Config** | `src/config/` | `dependencies.py`, `environment_variables.py` |

---

## Dependency Injection

Dependencies are managed via FastAPI's dependency injection with a singleton pattern:

```python
# In src/config/dependencies.py
class GlobalDependencies(metaclass=Singleton):
    database_async_read_write_engine: AsyncEngine
    temporal_client: TemporalClient
    mongodb_database: MongoDBDatabase
    redis_pool: redis.ConnectionPool

# In routes, use Annotated types
async def get_agent(
    agent_id: str,
    agents_use_case: DAgentsUseCase,  # Auto-injected
) -> AgentResponse:
    ...
```

This pattern ensures:

- Single connection pools shared across requests
- Easy testing via dependency overrides
- Clear dependency graphs
- Proper lifecycle management (startup/shutdown)
