"""add task failure source

Revision ID: f4d8c2b7a901
Revises: c4e8b2a7f91d
Create Date: 2026-08-26 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4d8c2b7a901"
down_revision: str | None = "c4e8b2a7f91d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS failure_source VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS failure_source")
