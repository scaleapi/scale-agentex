"""add_agents_registration_metadata_gin_index

Revision ID: b7d3e1f4a2c6
Revises: c4e8b2a7f91d
Create Date: 2026-09-03 12:00:00.000000

Supports the ``agent_card_metadata`` filter on ``GET /agents``, which applies a
JSONB containment predicate (``registration_metadata @> ...``). Discovery
clients poll that filtered endpoint, while agent registration writes are
comparatively rare. A ``jsonb_path_ops`` GIN index on the full
``registration_metadata`` column serves the containment operator directly, so
the polling read path does not degrade into a sequential scan as the agent
registry grows.

Safety:
- Index built with CREATE INDEX CONCURRENTLY inside an autocommit_block, so no
  long write lock is taken on ``agents``.
- IF NOT EXISTS on both upgrade and downgrade makes re-runs a no-op.
- ``jsonb_path_ops`` matches the query's ``@>`` operator and is smaller and
  faster for it than the default GIN opclass; the index intentionally covers
  the whole column rather than an expression, mirroring the existing
  ``ix_tasks_metadata_gin`` index and the exact predicate the repository emits.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3e1f4a2c6"
down_revision: str | None = "c4e8b2a7f91d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_agents_registration_metadata_gin"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} "
            "ON agents USING GIN (registration_metadata jsonb_path_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
