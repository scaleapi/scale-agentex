"""retire spans

Revision ID: 78384970fed5
Revises: c4e8b2a7f91d
Create Date: 2026-09-11 12:39:10.000000

Renames the legacy Postgres-backed spans table to spans_legacy. Agent spans
are written to the platform's tracing service by the SDK's SGP tracing
processor, and the /spans API that fed this table is removed in the same
change, so the server neither reads nor writes it any more. Clients on SDK
versions that still default to that API get a 404 per drained batch from
here on, logged by their span queue.

The table is renamed rather than dropped so its history stays recoverable
until an operator confirms it is not needed (export it with pg_dump -t
spans_legacy if it is). A later revision drops spans_legacy.

Safety:
- RENAME is a catalog update that does not touch rows, and it takes an
  AccessExclusiveLock on spans only. Its foreign key to tasks is kept, so
  no trigger on tasks is removed and tasks is not locked. A writer holding
  a conflicting lock on spans for longer than lock_timeout (an old pod
  mid-rollout) aborts the migration, and the pod retries it on its next
  start.
- IF EXISTS keeps re-runs idempotent. Indexes and the foreign key keep
  their names.
- Downgrade renames the table back, so the old routes find it again.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "78384970fed5"
down_revision: str | None = "c4e8b2a7f91d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS spans RENAME TO spans_legacy")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS spans_legacy RENAME TO spans")
