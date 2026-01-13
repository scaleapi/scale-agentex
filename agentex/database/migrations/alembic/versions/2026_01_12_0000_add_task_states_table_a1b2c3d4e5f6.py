"""add_task_states_table

Revision ID: a1b2c3d4e5f6
Revises: d024851e790c
Create Date: 2026-01-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d024851e790c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "agent_id", name="uq_task_states_task_agent"),
    )
    op.create_index("idx_task_states_task_id", "task_states", ["task_id"], unique=False)
    op.create_index(
        "idx_task_states_agent_id", "task_states", ["agent_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_task_states_agent_id", table_name="task_states")
    op.drop_index("idx_task_states_task_id", table_name="task_states")
    op.drop_table("task_states")
