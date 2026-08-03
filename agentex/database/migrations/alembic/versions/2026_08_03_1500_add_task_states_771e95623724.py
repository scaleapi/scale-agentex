"""add task_states

Revision ID: 771e95623724
Revises: a1b2c3d4e5f6
Create Date: 2026-08-03 15:00:00.000000

Creates the task_states table: the optional PostgreSQL backend for task state
(selected per deployment via TASK_STATE_STORAGE_PHASE; MongoDB remains the
default). Schema-only on a brand-new table, so creation is instant and holds
no lock against live traffic; nothing reads or writes the table until the
Postgres task-state repository lands.

The (task_id, agent_id) index is deliberately absent: its shape is the open
write-semantics decision (a unique constraint backing an atomic upsert, or a
plain compound index mirroring MongoDB) and it ships with that decision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "771e95623724"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("state", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Cascade is a dormant safety net: no current flow hard-deletes task
        # rows (API deletes are soft; retention deletes states explicitly and
        # keeps the task row).
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        # No cascade on agent_id: agents are never hard-deleted today, and
        # silently dropping an agent's states if that changed would be the
        # wrong default.
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # The index targets the table created in this same migration, so it holds
    # no write-blocking lock against live traffic (the table has no rows yet).
    op.create_index(
        "ix_task_states_agent_id",
        "task_states",
        ["agent_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_task_states_agent_id", table_name="task_states")
    op.drop_table("task_states")
