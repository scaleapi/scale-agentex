"""adding task cleaned at

Revision ID: 6c942325c828
Revises: a9959ebcbe98
Create Date: 2026-05-19 19:29:34.858692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c942325c828'
down_revision: Union[str, None] = 'a9959ebcbe98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('cleaned_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'cleaned_at')
