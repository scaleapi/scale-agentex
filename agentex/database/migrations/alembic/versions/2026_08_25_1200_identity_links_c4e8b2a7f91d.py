"""add identity_links

Revision ID: c4e8b2a7f91d
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25 12:00:00.000000

Creates the identity_links table: the Slack/Linear user -> SGP user mapping plus
that user's encrypted SGP credential, which together let an event-driven
invocation act as the invoking human rather than a shared bot.

Schema-only. There is nothing to backfill — the mapping cannot be derived from
existing data, since it only comes into being when a user authenticates both
identities in one moment. So no in-band UPDATE is possible even in principle.

Safety:
- Idempotent: the table create is guarded on a catalog check and the indexes use
  IF NOT EXISTS, so re-running is a no-op.
- Indexes built with CREATE UNIQUE INDEX CONCURRENTLY inside an autocommit_block.
  The table is empty here so a plain build would also be safe, but CONCURRENTLY
  keeps this consistent with the repo rule and removes the question.
- No foreign keys: sgp_user_id / sgp_account_id belong to SGP and provider ids
  are external, so there is nothing local to reference.
- credential_ciphertext holds Fernet output, never a plaintext credential. The
  encryption key is delivered via the platform secret mount, deliberately NOT
  stored in this database — a dump of this table alone is not enough to use the
  credentials.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8b2a7f91d"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "identity_links"

# Partial uniqueness scoped to active rows, because revocation is a tombstone:
#   - one active SGP identity per provider identity -> the mapping is a function
#   - one active provider identity per SGP user     -> defense in depth; two Slack
#     accounts aimed at one SGP user is the shape an identity hijack takes
_INDEXES = (
    (
        "uq_identity_links_external_active",
        "(provider, external_team_id, external_user_id)",
    ),
    (
        "uq_identity_links_sgp_user_active",
        "(provider, external_team_id, sgp_user_id)",
    ),
)


def _table_exists(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = :name"
            ),
            {"name": name},
        )
        .scalar()
    )


def upgrade() -> None:
    if not _table_exists(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(), nullable=False),
            # SQLAlchemy's Enum stores the member NAME, so these match the
            # IdentityProvider / IdentityLinkMethod member names.
            sa.Column(
                "provider",
                sa.Enum("SLACK", "LINEAR", name="identityprovider"),
                nullable=False,
            ),
            sa.Column("external_team_id", sa.String(length=64), nullable=False),
            sa.Column("external_user_id", sa.String(length=64), nullable=False),
            sa.Column("sgp_user_id", sa.String(length=64), nullable=False),
            sa.Column("sgp_account_id", sa.String(length=64), nullable=False),
            sa.Column(
                "linked_via",
                sa.Enum("EXPLICIT", "EMAIL_MATCH", "MANUAL", name="identitylinkmethod"),
                nullable=False,
            ),
            # Fernet ciphertext. Nullable: a mapping with no credential is still a
            # valid mapping, it just can't be acted through.
            sa.Column("credential_ciphertext", sa.Text(), nullable=True),
            sa.Column(
                "credential_expires_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "linked_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    # Outside the migration transaction: CREATE INDEX CONCURRENTLY cannot run
    # inside one. Entering the block commits the create above, so the indexes are
    # built against a committed table.
    with op.get_context().autocommit_block():
        for name, columns in _INDEXES:
            op.execute(
                f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON {_TABLE} {columns} WHERE revoked_at IS NULL"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _columns in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
    # Enum types are created implicitly by the columns above and aren't shared
    # with any other table, so they go with it.
    op.execute("DROP TYPE IF EXISTS identityprovider")
    op.execute("DROP TYPE IF EXISTS identitylinkmethod")
