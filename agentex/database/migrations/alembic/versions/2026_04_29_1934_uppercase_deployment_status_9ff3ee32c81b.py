"""uppercase deployment status enum labels

Rename the labels of the `deploymentstatus` Postgres enum from mixed-case
(`Pending`, `Ready`, `Failed`) to uppercase (`PENDING`, `READY`, `FAILED`)
so they match what SQLAlchemy binds by default (the enum member `.name`,
not `.value`). Without this, INSERTs from the ORM fail with
`InvalidTextRepresentationError: invalid input value for enum
deploymentstatus: "READY"`. Aligns with the convention used by the other
enums in this schema (agentstatus, agentinputtype, agentapikeytype).

Revision ID: 9ff3ee32c81b
Revises: 57c5ed4f59ae
Create Date: 2026-04-29 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '9ff3ee32c81b'
down_revision: Union[str, None] = '57c5ed4f59ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The column default references 'Pending' by name; drop it so the
    # rename below doesn't leave behind a broken default expression.
    op.execute("ALTER TABLE deployments ALTER COLUMN status DROP DEFAULT")

    op.execute("ALTER TYPE deploymentstatus RENAME VALUE 'Pending' TO 'PENDING'")
    op.execute("ALTER TYPE deploymentstatus RENAME VALUE 'Ready' TO 'READY'")
    op.execute("ALTER TYPE deploymentstatus RENAME VALUE 'Failed' TO 'FAILED'")

    op.execute(
        "ALTER TABLE deployments ALTER COLUMN status SET DEFAULT 'PENDING'::deploymentstatus"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deployments ALTER COLUMN status DROP DEFAULT")

    op.execute("ALTER TYPE deploymentstatus RENAME VALUE 'PENDING' TO 'Pending'")
    op.execute("ALTER TYPE deploymentstatus RENAME VALUE 'READY' TO 'Ready'")
    op.execute("ALTER TYPE deploymentstatus RENAME VALUE 'FAILED' TO 'Failed'")

    op.execute(
        "ALTER TABLE deployments ALTER COLUMN status SET DEFAULT 'Pending'::deploymentstatus"
    )
