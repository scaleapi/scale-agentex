"""add_agent_protocol_field

Revision ID: a064de6df78e
Revises: 4a9b7787ccd7
Create Date: 2026-04-07 15:38:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a064de6df78e"
down_revision: Union[str, None] = "4a9b7787ccd7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("protocol", sa.String(), nullable=False, server_default="acp"),
    )


def downgrade() -> None:
    op.drop_column("agents", "protocol")
