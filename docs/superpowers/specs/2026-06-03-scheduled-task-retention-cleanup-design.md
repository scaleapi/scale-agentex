# Scheduled Task-Retention Cleanup Workflow — Design

**Date:** 2026-06-03
**Status:** Approved (pending spec review)
**Author:** Stas Moreinis

## Background

A data-retention requirement calls for isolating project data and avoiding
long-lived chat/task data in the shared setup: keep Agentex chat/task data only
while a conversation is "active", and auto-clean it after a configurable idle
window (default 7 days since last interaction).

The export / clean / rehydrate building blocks already landed (PR #243):
`TaskRetentionUseCase` and `TaskRetentionService.clean_task(...)` are written so
that the same logic backs both the HTTP admin endpoints and a scheduled cleanup
caller. `clean_task` is **idempotent**, performs its own **authoritative idle
check** (`max(task.updated_at, latest_message.created_at) < now - idle_days`),
and **refuses** (raises `ClientError`) for three safety/policy cases: the task is
`RUNNING`, it is not idle long enough (when the threshold is enforced), or it has
unprocessed events past the `agent_task_tracker` cursors. If the task is already
cleaned (`cleaned_at IS NOT NULL`) it returns an empty result rather than raising.

This document designs the missing piece: a **regularly scheduled sweep** that
discovers idle tasks and drives them through `clean_task`.

### Scope (v1)

- **In scope:** A Temporal Schedule + sweep workflow that finds idle tasks
  belonging to an allowlisted set of agents and cleans them, gated by a feature
  flag. Clean only.
- **Out of scope (explicitly):**
  - Exporting task content to an external sink before cleanup. Per the retention
    discussion, v1 cleanup does **not** export anywhere; persisted chat history
    lives in the consuming product's approved store and the export/rehydrate APIs
    remain available for manual testing and a later full-restore path.
  - Rehydrate wiring.
  - **Deploying the Temporal worker in the target (k8s) environment.** The worker
    process and Schedule infrastructure exist in code and docker-compose, but the
    deployed environment may not yet run a backend Temporal worker. That is an
    infra prerequisite tracked separately; this design is the code change.

## Goals

1. Periodically clean idle tasks for an allowlisted set of agents, with zero
   behavior change in any environment until explicitly enabled.
2. Reuse the existing, idempotent `clean_task` path verbatim — no duplicated
   deletion logic.
3. Be resilient: one task's failure or refusal never aborts the sweep; the run
   is safe to retry and safe to replay after a worker crash.
4. Bound resource usage (Temporal history, concurrent deletes) regardless of
   backlog size.

## Configuration

All configuration is via environment variables (consistent with the existing
`ENABLE_HEALTH_CHECK_WORKFLOW` pattern). The master flag and cron are read at
**schedule-bootstrap** time; the allowlist and idle threshold are passed into the
scheduled workflow as input args so the schedule encodes the policy it runs with.

| Env var | Meaning | Default |
|---|---|---|
| `RETENTION_CLEANUP_ENABLED` | Master on/off. When false, the schedule is not created and the sweep is a no-op. | `false` |
| `RETENTION_CLEANUP_AGENT_ALLOWLIST` | Comma-separated agent **names**. Only tasks owned by these agents are eligible. Empty ⇒ nothing eligible (fail-closed). | `""` |
| `RETENTION_CLEANUP_IDLE_DAYS` | Idle threshold in days. | `7` |
| `RETENTION_CLEANUP_CRON` | Cron expression for the schedule. | `0 4 * * *` (daily 04:00) |
| `RETENTION_CLEANUP_PAGE_SIZE` | Candidate page size per discovery activity call. | `200` |
| `RETENTION_CLEANUP_MAX_IN_FLIGHT` | Max concurrent per-task child workflows. | `20` |

**Fail-closed:** an empty allowlist cleans nothing. The allowlist scopes the
blast radius to named agents only.

## Architecture

### Components

| Component | File | Responsibility |
|---|---|---|
| `RetentionCleanupSweepWorkflow` | `agentex/src/temporal/workflows/retention_cleanup_workflow.py` | Paginate candidates → fan out child workflows in bounded batches → aggregate summary → `continue_as_new` across pages. |
| `RetentionCleanupTaskWorkflow` | same file | Per-task child workflow: invoke the clean activity, return a structured outcome. |
| `RetentionCleanupActivities` | `agentex/src/temporal/activities/retention_cleanup_activities.py` | `find_cleanup_candidates(...)` and `clean_task(...)` (the latter catches `ClientError` and maps it to a `skipped` outcome). |
| Discovery query | `agentex/src/domain/repositories/task_repository.py` (extend) | Keyset-paginated query for idle, uncleaned candidate task ids filtered by agent name. |
| Schedule bootstrap | `agentex/src/temporal/run_retention_cleanup_schedule.py` | On startup, when enabled, create/update the Temporal Schedule (mirrors `run_healthcheck_workflow.py`). |
| Worker registration | `agentex/src/temporal/run_worker.py` (edit) | Register both workflows + the activities on the `agentex-server` task queue. |

### Data flow

```
Temporal Schedule (cron; created at bootstrap only when RETENTION_CLEANUP_ENABLED)
  └─> RetentionCleanupSweepWorkflow(idle_days, allowlist, page_size, max_in_flight)
        ├─ activity find_cleanup_candidates(cursor, limit, idle_days, allowlist) -> [task_id...]
        ├─ for each batch (size ≤ max_in_flight) of task_ids:
        │     start child RetentionCleanupTaskWorkflow(task_id, idle_days)
        │       └─ activity clean_task(task_id, idle_days)   # enforce_idle_threshold=True
        │            -> outcome: cleaned{counts} | skipped{reason}
        │               (raises only on transient/infra errors -> Temporal retries)
        ├─ accumulate running totals: cleaned / skipped(by reason) / failed
        └─ if another page exists: continue_as_new(next_cursor, running_totals)
           else: emit structured summary log and complete
```

### Discovery query

```sql
SELECT t.id
FROM tasks t
JOIN task_agents ta ON ta.task_id = t.id
JOIN agents a       ON a.id = ta.agent_id
WHERE t.cleaned_at IS NULL
  AND t.updated_at < (now() - make_interval(days => :idle_days))
  AND a.name = ANY(:allowlist)
  AND t.id > :cursor          -- keyset pagination
ORDER BY t.id
LIMIT :page_size;
```

Notes:

- **No `status` filter.** `status` is the race-prone dimension — a task can flip
  to `RUNNING` between this query and the clean call, so filtering it here gives
  only a false sense of safety. The trustworthy RUNNING check is the
  authoritative guard inside `clean_task` (evaluated at clean-time). Discovery is
  therefore limited to stable, index-friendly columns (`cleaned_at`,
  `updated_at`) plus the allowlist join; a rare RUNNING-but-stale task surfaces as
  a candidate and is absorbed as `skipped{reason=running}` by the backstop.
- The `updated_at < cutoff` pre-filter is a **correct superset** of genuinely-idle
  tasks: true idleness requires both `updated_at` **and** the latest Mongo message
  to predate the cutoff, so the Postgres pre-filter can never exclude a truly-idle
  task. It only over-includes (caught at clean-time), never under-includes.
- Keyset pagination by `id` (not OFFSET) keeps each page cheap and stable as rows
  are cleaned mid-sweep.

## Idleness & correctness

- **Pre-filter (cheap, in discovery):** `cleaned_at IS NULL AND updated_at < cutoff`.
- **Authoritative (correctness-critical, in `clean_task`):** idle check including
  the latest Mongo message timestamp, the RUNNING guard, and the unprocessed-events
  guard. The sweep always runs with `enforce_idle_threshold=True` and **never**
  forces.
- **Idempotency / replay safety:** `clean_task` no-ops on already-cleaned tasks and
  is idempotent across all stores, so child-workflow retries and worker-crash
  replays are safe.

## Error handling

- The `clean_task` activity **catches `ClientError`** (the three refusals) and
  returns a structured `skipped{reason}` outcome; the child workflow completes
  successfully. Pre-filtering keeps these rare; the catch handles the unavoidable
  races (a message/event landing between discovery and clean).
- Genuine transient errors (Postgres/Mongo) **propagate**, so Temporal's default
  RetryPolicy retries the activity. A child that still fails after retries is
  counted as `failed` by the parent and **does not abort the sweep**.
- The parent emits a structured summary log (`cleaned`, `skipped` by reason,
  `failed`) for Datadog faceting, consistent with the existing
  `task_cleanup_completed` forensic log emitted by `clean_task`.

## Scale & safety

- `continue_as_new` per page bounds workflow history irrespective of backlog size.
- `max_in_flight` caps concurrent child workflows to avoid a thundering herd of
  deletes against Mongo/Postgres.
- Feature flag ⇒ no behavior change anywhere until explicitly enabled.
- Allowlist (fail-closed) ⇒ blast radius limited to named agents.

## Testing

- **Unit:** discovery query filters and keyset paging; activity skip-mapping
  (`ClientError` → `skipped{reason}`); parent summary aggregation; fail-closed on
  empty allowlist.
- **Integration (testcontainers — Postgres/Mongo):** seed idle, active,
  already-cleaned, and not-yet-idle tasks across allowlisted and non-allowlisted
  agents; run the activity layer; assert only the right tasks are cleaned and that
  counts/skips match.
- **Workflow (Temporal `WorkflowEnvironment`):** fan-out correctness,
  `continue_as_new` paging across multiple pages, and that a failed child does not
  abort the sweep.

## Open prerequisites (not built here)

- Backend Temporal worker must actually run in the target deployed environment for
  the Schedule to execute. Tracked as an infra change separate from this code.
