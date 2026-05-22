# AgentEx subsection — ERD: SGP Service Decomposition and Catalog

| | |
|---|---|
| **Status** | Draft, in review |
| **Date** | 2026-05-22 |
| **Owner** | AgentEx team |
| **Parent doc** | ERD: SGP Service Decomposition and Catalog |

## Purpose of this document

This is the proposed AgentEx subsection of the parent ERD, written as a mini-ERD applied to the AgentEx backend (the FastAPI + Temporal service in `scale-agentex/agentex/`). The parent ERD decomposes `egp-api-backend` into fourteen services; the AgentEx slot in the catalog is currently a stub. This document fills that stub by treating the AgentEx backend as a smaller monolith and proposing its own decomposition into four services, mirroring the parent ERD's structure (Problem Statement, Solution Statement, Service Inventory, per-service catalog bullets, Open Questions).

Scope is the AgentEx backend only. `agentex-ui` and `agentex-agents/teams/*` are out of scope for this section.

## Problem Statement

The AgentEx backend (`scale-agentex/agentex/`) is a single FastAPI + Temporal service that today owns four distinct concerns inside one process and one set of data stores: a low-write **control plane** (agent registry, deployments, schedules, agent API keys), a **task lifecycle plane** (tasks, task agents, task tracker), a realtime **agent I/O surface** (messages, events, Redis-streams fanout), and an **agent-internal state surface** (per-task K/V state, LangGraph checkpoints). These four planes share one PostgreSQL cluster, one MongoDB cluster, one Redis instance, and one pod set sized for the worst of them.

The current shape has measurable costs:

- **Coupled scaling.** The agent I/O surface (messages + Redis streams) is realtime, fans out to UI subscribers, and scales with interactive session count. The agent-internal state surface scales with autonomous-agent step rate, which is much higher and bursty. The control plane is near-idle. Today all three share the same pods sized for the loudest of them.
- **Shared failure domain.** A Mongo problem on the messages collection can block the agent-internal state surface (also Mongo). A noisy write path can starve other writers. The agent registry — which is on the critical path of every task creation — shares a process with the data plane. Operating both PostgreSQL and MongoDB also means two databases to deploy, monitor, and back up for what are largely append-and-key-value workloads.

Spans are a related concern being addressed by other means: AgentEx will retire its `spans` table in favor of consuming `sgp-traces`, so spans are not a target of this decomposition.

## Solution Statement

Decompose the AgentEx backend into four services, each owning a coherent set of data and a coherent load profile. **`agentex-control-plane`** owns the agent registry and deployment registration surface — agents, deployments, deployment history, schedules, and agent API keys; low write rate, off the agent-execution hot path. **`agentex-tasks`** owns the task lifecycle — tasks, task→agent associations, and the agent task tracker; the canonical "what tasks exist and what state are they in" surface. **`agentex-conversations`** owns the realtime agent I/O surface — messages, events, and the Redis-streams fanout that carries them to UI subscribers; latency-sensitive, paired tightly with the streaming bus. **`agentex-state`** owns agent-internal data — per-task K/V state and LangGraph checkpoints; high write rate, written by the agent runtime for the agent runtime.

As part of this migration, AgentEx **evaluates Postgres as the source of truth for messages and task states**, with the intent to commit to Postgres if performance is comparable to MongoDB. Today, MongoDB hosts both collections; co-location means a Mongo incident affects two unrelated services post-decomposition, and operating Mongo alongside Postgres is duplicated tooling, monitoring, and backup surface for what is effectively two ordered append/key-value workloads that Postgres can serve well. The decomposition is the natural moment to validate the swap: each new service is the boundary at which its store choice can change without rippling. If the evaluation succeeds, the resulting topology runs on one fewer database; if performance does not meet bar, the services keep their MongoDB stores and the boundary work still stands. Comparable performance is defined as **within 5–10% of the MongoDB baseline on write throughput and p99 latency**. A load-test baseline for the existing MongoDB infrastructure will be established prior to extraction 1; the same load test will be executed against the candidate Postgres topology to evaluate the swap.

Sequence the extraction **leaves-first**, mirroring the parent ERD's protocol — pull `agentex-state` out first, then `agentex-conversations`, then `agentex-tasks`. After those three extractions, what remains in the agentex backend is `agentex-control-plane` by attrition; there is no separate extraction step for it, and further decomposition of the residual control plane can be revisited at that point if warranted. Each extraction follows the parent ERD's **per-service dress-rehearsal + physical-cutover** protocol: isolate the service's data within the shared source stores with restricted credentials, surface and fix cross-domain access violations, then cut over to dedicated infrastructure.

Spans are not included in this decomposition. The `spans` table is being retired in favor of consuming `sgp-traces`: the AgentEx SDK has already removed local spans as a default tracing processor, but the receiving plumbing in the backend remains because legacy SDK versions are still in use. The deprecation path is to gradually no-op the spans endpoints as legacy agents roll off, allowing the code to be removed without breaking outstanding clients.

## Service Inventory

| # | Split | Owns | Go | Recommend | Notes |
|---|---|---|---|---|---|
| 1 | `agentex-state` | `task_states`\* + `checkpoints` + `checkpoint_blobs` + `checkpoint_writes` + `checkpoint_migrations`; state and checkpoint routes | **Yes** | Yes | **Extract first.** Simplest surface; test-drives the per-service extraction protocol. High write rate (per-agent-step) — Go rewrite target for throughput. The HTTP checkpoint contract is already in place (PR #146): the SDK's `HttpCheckpointSaver` calls `/checkpoints/{get-tuple,put,put-writes,list,delete-thread}`, so the service boundary exists today — the Go service just needs to serve the same contract. |
| 2 | `agentex-conversations` | `messages`\* + `events` + Redis-streams fanout; message and event routes | **Yes** | Yes | **Extract second.** Realtime I/O surface — SDK's `send_message` / `send_event` / streaming `task_message_context` paths terminate here. High write + latency-sensitive — Go rewrite target. Second of the two Mongo-owning services, so the Mongo→Postgres evaluation completes here. |
| 3 | `agentex-tasks` | `tasks` + `task_agents` + `agent_task_tracker`; task lifecycle routes | No | Yes | **Extract third.** Canonical "what tasks exist and what state are they in" surface. Mid-throughput lifecycle CRUD; Python is fine, no Go affinity. Depends only on `agentex-control-plane` for inbound FKs. |
| 4 | `agentex-control-plane` | `agents` + `deployments` + `deployment_history` + `schedules` + `agent_api_keys`; agent registration, deployment registration, schedule, API-key routes | No | Yes | **Residual.** What remains in the agentex backend after rows 1–3 are extracted. No separate extraction step. Hosts the AgentEx Temporal worker on a single task queue. Further decomposition revisited at that point if warranted. |

> \* `messages` and `task_states` live in MongoDB today. The Mongo→Postgres swap is committed-conditional-on-performance per the Solution Statement; if performance does not meet bar, these services keep their MongoDB stores and the service boundaries still stand.

> Note: `agentex-auth` is an existing AgentEx-owned service that already runs separately and is not part of this decomposition. It is included in the per-service catalog bullets below for completeness.

## Per-service catalog bullets

These are the bullets that drop into the "All-up SGP Service Catalog" section of the parent ERD under the AgentEx subsection.

> **`agentex-state`.** Owns `task_states` (Mongo today, Postgres pending evaluation) and the LangGraph checkpointer tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`). Per-task K/V state and graph-checkpoint storage for the AgentEx runtime; high write rate, written by the agent runtime for the agent runtime. The HTTP checkpoint contract is already in place — the AgentEx SDK calls the backend's `/checkpoints/*` endpoints via `HttpCheckpointSaver` rather than connecting to Postgres directly, so the service boundary exists today. Go service. Outbound: `agentex-tasks` (task scope validation), `agentex-auth` (authn / authz).
>
> **`agentex-conversations`.** Owns `messages` (Mongo today, Postgres pending evaluation), `events`, and the Redis-streams fanout that carries them to UI subscribers. The realtime agent I/O surface — the SDK's `send_message`, `send_event`, and streaming `task_message_context` paths terminate here. Latency-sensitive, paired tightly with the streaming bus. Go service. Outbound: `agentex-tasks` (task scope validation), `agentex-auth` (authn / authz).
>
> **`agentex-tasks`.** Owns `tasks`, `task_agents`, `agent_task_tracker`; task lifecycle routes including the cron-triggered task creation surface that pairs with control-plane schedules. The canonical "what tasks exist and what state are they in" surface; read by `agentex-state` and `agentex-conversations`. Python service. Outbound: `agentex-control-plane` (agent registry lookups), `agentex-auth` (authn / authz).
>
> **`agentex-control-plane`.** The residual AgentEx backend after the three extractions above. Owns `agents`, `deployments`, `deployment_history`, `schedules`, `agent_api_keys`; agent registration and lifecycle, deployment registration (the in-cluster registry of what version is currently registered and serving — distinct from `sgp-agent-deploy`'s build/push pipeline), cron schedules, and agent-scoped API key management. Hosts the AgentEx Temporal worker on a single task queue. Other AgentEx services do not use Temporal post-decomposition; if a future service needs it, it gets its own service-specific queue. Python service. Outbound: `agentex-auth` (authn / authz).
>
> **`agentex-auth`.** Existing AgentEx-owned authentication and authorization service; exposes `/v1/authn` and `/v1/authz/{grant,revoke,check,search}`. All AgentEx services authenticate and authorize requests against `agentex-auth` directly. Outbound: `sgp-identity` (delegated identity verification). Future direction may fold `agentex-auth` into `sgp-identity` as part of OneAuth — see Open Questions.

## Open Questions

1. **`agentex-auth` ↔ `sgp-identity` fold-in via OneAuth.** Today `agentex-auth` is a standalone AgentEx service that AgentEx services call directly and which delegates identity verification to `sgp-identity` underneath. The OneAuth direction may consolidate `agentex-auth` into `sgp-identity`, but the decision is not committed. Affects whether AgentEx services continue calling `agentex-auth` long-term or eventually call `sgp-identity` directly, and whether `agentex-auth`'s authz-policy responsibilities move with it.

2. **Checkpoint lift-out trigger.** `agentex-state` bundles LangGraph checkpoints with general K/V state. Lift `checkpoints` into a separate `agentex-checkpoints` service if (a) non-LangGraph graph runtimes are adopted, or (b) checkpoint write rate dominates the service. Specific criteria to be sharpened in a follow-up.

3. **`agentex-control-plane` ↔ `sgp-agent-deploy` boundary.** `sgp-agent-deploy` (per parent ERD) owns `agentex_cloud_builds`, `agentex_cloud_deploys`, `agentex_permissions` — the build/push pipeline. `agentex-control-plane` owns `deployments` + `deployment_history` — the in-cluster runtime registry of "what version is currently registered and serving." Pin the handoff between "build artifact ready" and "live agent registered and serving" so the contract is unambiguous.
