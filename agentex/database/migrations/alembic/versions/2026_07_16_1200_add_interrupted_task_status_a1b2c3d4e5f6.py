"""add interrupted task status

Revision ID: a1b2c3d4e5f6
Revises: 9a4b8c7d6e5f
Create Date: 2026-07-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9a4b8c7d6e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New non-terminal task status: the current turn was interrupted by the user
    # and the task is waiting for the next message (see task/interrupt).
    op.execute("""
        ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'INTERRUPTED';
    """)


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type, so there is
    # nothing to do on downgrade (mirrors the soft_delete_status migration).
    pass
