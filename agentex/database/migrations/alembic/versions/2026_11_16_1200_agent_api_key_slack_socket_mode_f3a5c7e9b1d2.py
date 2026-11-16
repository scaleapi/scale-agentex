"""agent api key slack socket mode

Revision ID: f3a5c7e9b1d2
Revises: e2f4a6c8b0d1
Create Date: 2026-11-16 12:00:00.000000

Adds two nullable columns to ``agent_api_keys`` so a Slack webhook trigger can be
served over Socket Mode: the encrypted app-level token and the agent subpath to
forward to. Metadata-only (nullable, no default, no backfill); IF NOT EXISTS makes
a re-run a no-op.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a5c7e9b1d2"
down_revision: str | None = "e2f4a6c8b0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_api_keys "
        "ADD COLUMN IF NOT EXISTS app_token_encrypted VARCHAR, "
        "ADD COLUMN IF NOT EXISTS forward_path VARCHAR;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE agent_api_keys "
        "DROP COLUMN IF EXISTS forward_path, "
        "DROP COLUMN IF EXISTS app_token_encrypted;"
    )
