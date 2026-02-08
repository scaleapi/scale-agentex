"""create_task_agent_join_table

Revision ID: bc9b04a3f508
Revises: 7736391266fa
Create Date: 2025-06-15 23:40:31.977258

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bc9b04a3f508"
down_revision: Union[str, None] = "7736391266fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the join table
    op.create_table(
        "task_agents",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("task_id", "agent_id"),
    )

    # Migrate existing data from tasks.agent_id to task_agents join table
    op.execute("""
        INSERT INTO task_agents (task_id, agent_id, created_at)
        SELECT id, agent_id, created_at FROM tasks WHERE agent_id IS NOT NULL
    """)

    # Drop the foreign key constraint first
    op.drop_constraint("tasks_agent_id_fkey", "tasks", type_="foreignkey")

    # Drop the agent_id column
    op.drop_column("tasks", "agent_id")


def downgrade() -> None:
    # Add back the agent_id column
    op.add_column("tasks", sa.Column("agent_id", sa.String(), nullable=True))

    # Migrate data back from join table to tasks.agent_id (taking first agent if multiple)
    op.execute("""
        UPDATE tasks 
        SET agent_id = (
            SELECT agent_id 
            FROM task_agents 
            WHERE task_agents.task_id = tasks.id 
            LIMIT 1
        )
    """)

    # Make agent_id not nullable and add foreign key constraint
    op.alter_column("tasks", "agent_id", nullable=False)
    op.create_foreign_key(
        "tasks_agent_id_fkey", "tasks", "agents", ["agent_id"], ["id"]
    )

    # Drop the join table
    op.drop_table("task_agents")
