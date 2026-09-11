"""drop spans

Revision ID: 78384970fed5
Revises: c4e8b2a7f91d
Create Date: 2026-09-11 12:39:10.000000

Drops the legacy Postgres-backed spans table. Agent spans are written to the
platform's tracing service by the SDK's SGP tracing processor, and the
/spans API that fed this table is removed in the same change, so nothing
reads or writes it any more.

Safety:
- DROP TABLE is metadata-only in PostgreSQL (the files are unlinked), so it
  completes well inside the statement timeout regardless of table size. It
  needs an AccessExclusiveLock; a writer still holding the table (an old pod
  mid-rollout) makes the lock wait hit lock_timeout, and the pod retries the
  migration on its next start.
- IF EXISTS keeps re-runs idempotent. The indexes and the foreign key to
  tasks go with the table.
- Downgrade recreates the empty table with the shape the ORM last declared.
  Indexes on a table created in the same migration are built plain, since
  there are no writers to block.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "78384970fed5"
down_revision: str | None = "c4e8b2a7f91d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS spans")


def downgrade() -> None:
    op.create_table(
        "spans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column(
            "task_id",
            sa.String(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL", name="fk_spans_task_id_tasks"),
            nullable=True,
        ),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
    )
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_trace_id_start_time", "spans", ["trace_id", "start_time"])
    op.create_index("ix_spans_parent_id", "spans", ["parent_id"])
    op.create_index("ix_spans_task_id", "spans", ["task_id"])
