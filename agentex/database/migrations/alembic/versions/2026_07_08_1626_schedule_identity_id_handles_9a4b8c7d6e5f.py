"""move run schedule identity to row id

Revision ID: 9a4b8c7d6e5f
Revises: e7f8a9b0c1d2
Create Date: 2026-07-08 16:26:00.000000

Switches schedule names from reserved external handles to mutable labels by
making the name uniqueness constraint apply only to active rows. Schema-only and
idempotent: index creation/drop use CONCURRENTLY with IF EXISTS / IF NOT EXISTS.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a4b8c7d6e5f"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_agent_run_schedules_active_agent_name "
            "ON agent_run_schedules (agent_id, name) "
            "WHERE deleted_at IS NULL"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS uq_agent_run_schedules_agent_name"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_agent_run_schedules_agent_name "
            "ON agent_run_schedules (agent_id, name)"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "uq_agent_run_schedules_active_agent_name"
        )
