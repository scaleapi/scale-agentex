"""add_tasks_metadata_gin_index

Revision ID: e9c4ff9e6542
Revises: 9ff3ee32c81b
Create Date: 2026-05-04 11:11:35.017451

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e9c4ff9e6542'
down_revision: Union[str, None] = '9ff3ee32c81b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tasks_metadata_gin "
            "ON tasks USING GIN (task_metadata jsonb_path_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_tasks_metadata_gin")
