"""add task current_state

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Opaque label mirroring an agent's StateMachine current state. Nullable and
    # additive; agents opt in by emitting it. Metadata-only add, non-blocking.
    op.add_column('tasks', sa.Column('current_state', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'current_state')
