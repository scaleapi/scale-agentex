# Runbook: backfill `spans.task_id` from `trace_id`

## Purpose

Populate the `spans.task_id` column on historical rows with the value from
`trace_id`, where `trace_id` matches an existing `tasks.id`. The column is
written natively by current clients; existing rows still have
`task_id = NULL`.

**This backfill is optional.** `SpanRepository.list` ORs on `trace_id` when
filtering by `task_id`, so application reads are correct without it. Run this
runbook only when:

- We want to drop the `trace_id` fallback in the application (cleanup goal).
- A downstream consumer specifically needs `WHERE task_id IS NOT NULL` to
  identify task-scoped spans for historical data.

## Background

An earlier in-band attempt to backfill this column via Alembic ran a single
large `UPDATE` inside Alembic's transaction on a multi-tens-of-GB `spans`
table. It held row locks and exhausted the application connection pool while
concurrent span writes piled up, taking the service offline until the
migration was killed.

This runbook does the same work in **batched, committed-per-batch chunks**
with explicit operator control over timing.

## Pre-flight

> Run all queries against the agentex database.

1. Confirm the migration that adds the column has been applied:

   ```sql
   SELECT version_num FROM alembic_version;
   ```

   Expected: `a9959ebcbe98` (or later). If the value is `4a9b7787ccd7` or
   earlier, **stop** — deploy the migration first.

2. Confirm the column exists and the FK + index are in place:

   ```sql
   \d spans
   ```

   Expected: `task_id` column, `fk_spans_task_id_tasks` constraint,
   `ix_spans_task_id` index.

3. Measure the size of the backlog:

   ```sql
   SELECT
       count(*) FILTER (WHERE s.task_id IS NULL AND t.id IS NOT NULL) AS to_backfill,
       count(*) FILTER (WHERE s.task_id IS NULL AND t.id IS NULL)     AS untouched_non_task_spans,
       count(*) FILTER (WHERE s.task_id IS NOT NULL)                  AS already_set,
       count(*)                                                       AS total
   FROM spans s
   LEFT JOIN tasks t ON t.id = s.trace_id;
   ```

   Note the `to_backfill` number. With 10 000 rows per batch and 100 ms
   sleep between batches, expect roughly 1 000 batches per minute. A
   ~25M-row backlog is therefore ~25 minutes of wall-clock time at the
   default pace.

4. Confirm there is no other long-running write or maintenance activity on
   the `spans` table:

   ```sql
   SELECT pid, now() - xact_start AS duration, state, wait_event, query
   FROM pg_stat_activity
   WHERE query ILIKE '%spans%'
     AND state <> 'idle'
   ORDER BY duration DESC;
   ```

## Coordination requirements

- Notify the operating team before starting and post the `to_backfill`
  count from step 3.
- Run during a confirmed low-traffic window, or shift traffic away from the
  service for the duration.
- Get sign-off from infra/platform.
- Have a rollback plan ready — the script below is safely cancellable
  (Ctrl-C in psql, then run the cancel snippet); no schema change happens.

## Execution

Connect to the agentex DB with `psql` (not via the application), and run:

```sql
-- 1. Apply per-session timeouts. lock_timeout fails fast if any other
--    session holds AccessExclusiveLock on spans (e.g. a stuck migration).
--    statement_timeout caps the *per-batch* runtime; total runtime is
--    unbounded because we loop and commit between batches.
SET lock_timeout = '3s';
SET statement_timeout = '60s';

-- 2. Loop in 10 000-row chunks. ROW_COUNT is checked between iterations to
--    detect when the backlog is drained. Each iteration commits before the
--    next starts, so autovacuum can reclaim dead tuples and the table
--    does not bloat.
DO $$
DECLARE
    rows_updated INT := 1;
    total_updated BIGINT := 0;
BEGIN
    WHILE rows_updated > 0 LOOP
        WITH batch AS (
            SELECT s.ctid
            FROM spans s
            JOIN tasks t ON t.id = s.trace_id
            WHERE s.task_id IS NULL
            LIMIT 10000
        )
        UPDATE spans
        SET task_id = trace_id
        WHERE ctid IN (SELECT ctid FROM batch);

        GET DIAGNOSTICS rows_updated = ROW_COUNT;
        total_updated := total_updated + rows_updated;

        RAISE NOTICE 'updated batch: % rows (running total: %)',
            rows_updated, total_updated;

        COMMIT;
        PERFORM pg_sleep(0.1);
    END LOOP;
END$$;
```

Notes on the SQL choices:

- `ctid` selection in a CTE means each batch operates on a fixed set of rows
  selected at the start of the batch — we don't read and write the same row
  in a single statement, and we don't hold locks across batches.
- `JOIN tasks` filters out spans whose `trace_id` is not actually a task id
  (system or framework spans). Those rows stay with `task_id = NULL`, which
  matches the application's existing semantics.
- The `COMMIT` inside the `DO` block requires PostgreSQL ≥ 11. Confirm the
  server version with `SELECT version();` if running this in an older env.
- `pg_sleep(0.1)` gives autovacuum and concurrent writes breathing room.

### Monitoring while it runs

In a separate `psql` session:

```sql
-- Live progress (rerun periodically)
SELECT count(*) AS remaining
FROM spans s JOIN tasks t ON t.id = s.trace_id
WHERE s.task_id IS NULL;

-- Active sessions on spans
SELECT pid, now() - xact_start AS duration, state, wait_event, left(query, 80)
FROM pg_stat_activity
WHERE query ILIKE '%spans%' AND state <> 'idle'
ORDER BY duration DESC;

-- Lock contention
SELECT pg_class.relname, pg_locks.mode, pg_locks.granted, pg_locks.pid
FROM pg_locks
JOIN pg_class ON pg_class.oid = pg_locks.relation
WHERE pg_class.relname = 'spans';
```

## Cancellation

The script is safe to interrupt at any batch boundary — already-committed
batches are durable; in-flight batches roll back cleanly.

- **From the same psql session**: Ctrl-C cancels the current statement.
- **From another session**, if the runner is stuck:

  ```sql
  -- Cancel the runner gracefully (releases locks at end of current batch)
  SELECT pg_cancel_backend(<pid>);

  -- If pg_cancel_backend doesn't return control, escalate:
  SELECT pg_terminate_backend(<pid>);
  ```

  Prefer `pg_cancel_backend` for this batched runbook;
  `pg_terminate_backend` should be reserved for situations where graceful
  cancellation has already failed.

## Exit criteria

The backfill is complete when both of the following return `0`:

```sql
SELECT count(*) AS remaining_to_backfill
FROM spans s JOIN tasks t ON t.id = s.trace_id
WHERE s.task_id IS NULL;
```

```sql
-- Sanity: no orphaned task_ids (FK is NOT VALID, so this is the only
-- way to verify referential cleanliness for backfilled rows).
SELECT count(*) AS orphaned_task_ids
FROM spans
WHERE task_id IS NOT NULL
  AND task_id NOT IN (SELECT id FROM tasks);
```

Once both are zero, notify the operating team and restore normal traffic
(if it was diverted).

## Follow-ups after a successful backfill

- Open a PR to drop the `trace_id` OR-fallback in
  `SpanRepository.list` — task-scoped spans can now be queried purely by
  `task_id`.
- Optionally run `ALTER TABLE spans VALIDATE CONSTRAINT fk_spans_task_id_tasks`
  to convert the FK from `NOT VALID` to `VALID`. This takes a
  `ShareUpdateExclusiveLock` (does **not** block reads/writes) and scans the
  table once. Coordinate with infra; a multi-tens-of-GB scan is non-trivial
  even when non-blocking.

## What this runbook deliberately does *not* do

- It does **not** modify any schema. The column, FK, and index are managed
  by the alembic migrations.
- It does **not** populate `task_id` for spans whose `trace_id` is not a
  task id. Those rows correctly remain `NULL`.
- It does **not** run from inside a deploy or pod-startup path. Migrations
  run on agentex pod startup; a multi-minute backfill in that path would
  recreate the original failure mode.
