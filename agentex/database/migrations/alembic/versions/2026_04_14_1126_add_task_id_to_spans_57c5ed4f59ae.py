"""add_task_id_to_spans

Revision ID: 57c5ed4f59ae
Revises: 4a9b7787ccd7
Create Date: 2026-04-14 11:26:45.193515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57c5ed4f59ae'
down_revision: Union[str, None] = '4a9b7787ccd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable task_id column first (no FK yet, so backfill can run freely)
    op.add_column('spans', sa.Column('task_id', sa.String(), nullable=True))

    # Backfill task_id from trace_id where trace_id is a valid task ID.
    # Uses a JOIN instead of a subquery for efficient matching.
    op.execute("""
        UPDATE spans
        SET task_id = spans.trace_id
        FROM tasks
        WHERE spans.trace_id = tasks.id
          AND spans.task_id IS NULL
    """)

    # Add FK constraint after backfill (NULL values are allowed by FK)
    op.create_foreign_key(
        'fk_spans_task_id_tasks',
        'spans',
        'tasks',
        ['task_id'],
        ['id'],
    )

    # Add index for querying spans by task_id
    op.create_index('ix_spans_task_id', 'spans', ['task_id'])


def downgrade() -> None:
    op.drop_index('ix_spans_task_id', table_name='spans')
    op.drop_constraint('fk_spans_task_id_tasks', 'spans', type_='foreignkey')
    op.drop_column('spans', 'task_id')
