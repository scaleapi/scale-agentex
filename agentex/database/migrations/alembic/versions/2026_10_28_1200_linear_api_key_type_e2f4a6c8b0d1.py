"""linear api key type

Revision ID: e2f4a6c8b0d1
Revises: b7d3e1f4a2c6
Create Date: 2026-10-28 12:00:00.000000

Adds LINEAR to ``agentapikeytype`` for the ``linear`` webhook-trigger source
(a Linear OAuth app's webhook signing secret, verified on /agents/forward),
the same way 17c57fe68d04 added SLACK. ADD VALUE IF NOT EXISTS makes a re-run
a no-op; Postgres cannot drop an enum value, so the downgrade leaves it.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f4a6c8b0d1"
down_revision: str | None = "b7d3e1f4a2c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE agentapikeytype ADD VALUE IF NOT EXISTS 'LINEAR';")


def downgrade() -> None:
    pass
