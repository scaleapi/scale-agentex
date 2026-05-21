"""add_task_id_to_spans

Revision ID: 57c5ed4f59ae
Revises: 4a9b7787ccd7
Create Date: 2026-04-14 11:26:45.193515

The original version of this migration also ran a large UPDATE backfill,
added a foreign key (which scanned the full table under AccessExclusiveLock),
and created an index non-concurrently. On a sufficiently large spans table
this can exhaust the connection pool while concurrent span writes pile up
behind the lock.

The backfill, FK and index are now handled out-of-band (see
docs/runbooks/spans-task-id-backfill.md) and a follow-up tail migration
finalizes the FK + index with non-blocking operations. This revision is
reduced to the only safe in-band step: adding the nullable column. Adding a
nullable column with no default is a metadata-only operation in PostgreSQL
>= 11, so it is fast and does not block writes.

The IF NOT EXISTS guard makes the migration safe to re-run on environments
where the original (heavier) version of this migration already completed
successfully.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '57c5ed4f59ae'
down_revision: Union[str, None] = '4a9b7787ccd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE spans ADD COLUMN IF NOT EXISTS task_id VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE spans DROP COLUMN IF EXISTS task_id")
