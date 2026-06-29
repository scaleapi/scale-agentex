"""backfill agent_run_schedules deleted_at/version columns

Revision ID: e7f8a9b0c1d2
Revises: 3b1c9d2e4f6a
Create Date: 2026-06-29 19:30:00.000000

Forward-fix for environments where revision 3b1c9d2e4f6a ran in an *earlier*
form of its file, before ``deleted_at`` and ``version`` were added to its
``create_table``. Those environments have the table stamped at 3b1c9d2e4f6a but
are missing the two columns, so the ORM (which selects both) fails with
``UndefinedColumnError``. Per the repo migration policy we do not rewrite the
already-applied revision; we add the columns here, idempotently.

Schema-only and idempotent: ``ADD COLUMN IF NOT EXISTS`` is a no-op on
environments that ran the final ``create_table`` (columns already present) and
repairs the ones that didn't. Both columns add with a constant/non-volatile
default (or are nullable), so on modern Postgres this is a metadata-only change
with no table rewrite.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "3b1c9d2e4f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Soft-delete marker: NULL = active, set = tombstoned for audit.
    op.execute(
        "ALTER TABLE agent_run_schedules "
        "ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE"
    )
    # Monotonic record version reserved for future optimistic concurrency.
    op.execute(
        "ALTER TABLE agent_run_schedules "
        "ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_run_schedules DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE agent_run_schedules DROP COLUMN IF EXISTS deleted_at")
