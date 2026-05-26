"""add_agent_api_key_creator_and_zedtoken

Revision ID: b2c84edb77d6
Revises: 6c942325c828
Create Date: 2026-05-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c84edb77d6'
down_revision: Union[str, None] = '6c942325c828'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_api_keys', sa.Column('creator_user_id', sa.String(), nullable=True))
    op.add_column('agent_api_keys', sa.Column('creator_service_account_id', sa.String(), nullable=True))
    op.add_column('agent_api_keys', sa.Column('spark_authz_zedtoken', sa.Text(), nullable=True))
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_api_keys_creator_user_id "
            "ON agent_api_keys (creator_user_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_api_keys_creator_service_account_id "
            "ON agent_api_keys (creator_service_account_id)"
        )
    op.create_check_constraint(
        'ck_agent_api_keys_one_creator',
        'agent_api_keys',
        '(creator_user_id IS NULL) OR (creator_service_account_id IS NULL)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_agent_api_keys_one_creator', 'agent_api_keys', type_='check')
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_api_keys_creator_service_account_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_api_keys_creator_user_id")
    op.drop_column('agent_api_keys', 'spark_authz_zedtoken')
    op.drop_column('agent_api_keys', 'creator_service_account_id')
    op.drop_column('agent_api_keys', 'creator_user_id')
