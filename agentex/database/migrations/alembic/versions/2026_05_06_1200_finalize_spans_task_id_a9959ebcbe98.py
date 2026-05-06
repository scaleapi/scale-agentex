"""finalize_spans_task_id

Revision ID: a9959ebcbe98
Revises: e9c4ff9e6542
Create Date: 2026-05-06 12:00:00.000000

Finalizes the spans.task_id column added in 57c5ed4f59ae by attaching the
foreign key and creating the lookup index using non-blocking operations.

This migration is intentionally split out from 57c5ed4f59ae so that:

  * The FK is added with NOT VALID, which acquires only a brief lock and
    skips the full-table scan that the original migration triggered. The FK
    is still enforced on all subsequent inserts and updates (and ON DELETE
    SET NULL still applies to existing rows).
  * The index is built CONCURRENTLY so writes are not blocked.
  * Both operations live in autocommit_block() so they run outside the
    surrounding migration transaction (CONCURRENTLY cannot run inside a
    transaction).

The migration is idempotent: on environments where the original version of
57c5ed4f59ae completed successfully (the FK and index already exist), each
operation is a no-op via IF NOT EXISTS / pg_constraint catalog checks.

The historical backfill of task_id from trace_id is intentionally not run
here — it is a separate, operator-driven step (see
docs/runbooks/spans-task-id-backfill.md). The application reads tolerate
NULL task_id by falling back to trace_id at query time.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a9959ebcbe98'
down_revision: Union[str, None] = 'e9c4ff9e6542'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_spans_task_id_tasks'
                ) THEN
                    ALTER TABLE spans
                    ADD CONSTRAINT fk_spans_task_id_tasks
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                    ON DELETE SET NULL
                    NOT VALID;
                END IF;
            END$$;
            """
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_spans_task_id "
            "ON spans (task_id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_spans_task_id")
        op.execute(
            "ALTER TABLE spans DROP CONSTRAINT IF EXISTS fk_spans_task_id_tasks"
        )
