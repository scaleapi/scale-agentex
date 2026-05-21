"""add_langgraph_checkpoint_tables

Revision ID: d1a6cde41b3f
Revises: d024851e790c
Create Date: 2026-02-11 08:02:10.739927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd1a6cde41b3f'
down_revision: Union[str, None] = 'd024851e790c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # checkpoint_migrations
    op.create_table('checkpoint_migrations',
    sa.Column('v', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('v')
    )

    # checkpoints
    op.create_table('checkpoints',
    sa.Column('thread_id', sa.Text(), nullable=False),
    sa.Column('checkpoint_ns', sa.Text(), server_default='', nullable=False),
    sa.Column('checkpoint_id', sa.Text(), nullable=False),
    sa.Column('parent_checkpoint_id', sa.Text(), nullable=True),
    sa.Column('type', sa.Text(), nullable=True),
    sa.Column('checkpoint', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id')
    )
    op.create_index('checkpoints_thread_id_idx', 'checkpoints', ['thread_id'], unique=False)

    # checkpoint_blobs
    op.create_table('checkpoint_blobs',
    sa.Column('thread_id', sa.Text(), nullable=False),
    sa.Column('checkpoint_ns', sa.Text(), server_default='', nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('version', sa.Text(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('blob', sa.LargeBinary(), nullable=True),
    sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'channel', 'version')
    )
    op.create_index('checkpoint_blobs_thread_id_idx', 'checkpoint_blobs', ['thread_id'], unique=False)

    # checkpoint_writes
    op.create_table('checkpoint_writes',
    sa.Column('thread_id', sa.Text(), nullable=False),
    sa.Column('checkpoint_ns', sa.Text(), server_default='', nullable=False),
    sa.Column('checkpoint_id', sa.Text(), nullable=False),
    sa.Column('task_id', sa.Text(), nullable=False),
    sa.Column('idx', sa.Integer(), nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('type', sa.Text(), nullable=True),
    sa.Column('blob', sa.LargeBinary(), nullable=False),
    sa.Column('task_path', sa.Text(), server_default='', nullable=False),
    sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id', 'task_id', 'idx')
    )
    op.create_index('checkpoint_writes_thread_id_idx', 'checkpoint_writes', ['thread_id'], unique=False)

    # Pre-populate checkpoint_migrations so LangGraph sees all its
    # internal migrations as already applied and skips setup().
    op.execute(
        sa.text(
            "INSERT INTO checkpoint_migrations (v) VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)"
        )
    )


def downgrade() -> None:
    op.drop_index('checkpoint_writes_thread_id_idx', table_name='checkpoint_writes')
    op.drop_table('checkpoint_writes')
    op.drop_index('checkpoint_blobs_thread_id_idx', table_name='checkpoint_blobs')
    op.drop_table('checkpoint_blobs')
    op.drop_index('checkpoints_thread_id_idx', table_name='checkpoints')
    op.drop_table('checkpoints')
    op.drop_table('checkpoint_migrations')
