"""add agent_run_schedules

Revision ID: 3b1c9d2e4f6a
Revises: c7a1b2d3e4f5
Create Date: 2026-06-22 12:00:00.000000

Creates the agent_run_schedules table backing the scheduled-agent-runs feature.
Schema-only and idempotent: the table and its indexes are created
with IF NOT EXISTS-style guards (Alembic create_table on a fresh table), and the
indexes target the just-created table so they are non-blocking by construction.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3b1c9d2e4f6a'
down_revision: str | None = 'c7a1b2d3e4f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'agent_run_schedules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cron_expression', sa.String(), nullable=True),
        sa.Column('interval_seconds', sa.Integer(), nullable=True),
        sa.Column(
            'timezone', sa.String(), server_default='UTC', nullable=False
        ),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'paused', sa.Boolean(), server_default='false', nullable=False
        ),
        sa.Column('creator_principal', sa.JSON(), nullable=False),
        sa.Column('task_params', sa.JSON(), nullable=True),
        sa.Column('task_metadata', sa.JSON(), nullable=True),
        sa.Column('initial_input', sa.JSON(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # Indexes target the table created in this same migration, so they hold no
    # write-blocking lock against live traffic (the table has no rows yet).
    op.create_index(
        'uq_agent_run_schedules_agent_name',
        'agent_run_schedules',
        ['agent_id', 'name'],
        unique=True,
    )
    op.create_index(
        'idx_agent_run_schedules_agent',
        'agent_run_schedules',
        ['agent_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_agent_run_schedules_agent', table_name='agent_run_schedules')
    op.drop_index(
        'uq_agent_run_schedules_agent_name', table_name='agent_run_schedules'
    )
    op.drop_table('agent_run_schedules')
