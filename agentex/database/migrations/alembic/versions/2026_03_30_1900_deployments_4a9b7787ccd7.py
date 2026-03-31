"""deployments

Revision ID: 4a9b7787ccd7
Revises: d1a6cde41b3f
Create Date: 2026-03-30 19:00:35.962651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a9b7787ccd7'
down_revision: Union[str, None] = 'd1a6cde41b3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create deployments table
    op.create_table('deployments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(length=64), nullable=False),
        sa.Column('docker_image', sa.String(), nullable=False),
        sa.Column('commit_hash', sa.String(), nullable=True),
        sa.Column('branch_name', sa.String(), nullable=True),
        sa.Column('author_name', sa.String(), nullable=True),
        sa.Column('author_email', sa.String(), nullable=True),
        sa.Column('build_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Enum('Pending', 'Ready', 'Failed', name='deploymentstatus'), nullable=False, server_default='Pending'),
        sa.Column('acp_url', sa.String(), nullable=True),
        sa.Column('is_production', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('sgp_deploy_id', sa.String(), nullable=True),
        sa.Column('helm_release_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_deployments_agent_id', 'deployments', ['agent_id'], unique=False)
    op.create_index('idx_deployments_agent_production', 'deployments', ['agent_id', 'is_production'], unique=False)
    op.create_index('idx_deployments_sgp_deploy_id', 'deployments', ['sgp_deploy_id'], unique=False)

    # 2. Add production_deployment_id to agents table
    op.add_column('agents', sa.Column('production_deployment_id', sa.String(), nullable=True))
    op.create_foreign_key('fk_agents_production_deployment', 'agents', 'deployments', ['production_deployment_id'], ['id'])


def downgrade() -> None:
    # Remove production_deployment_id from agents
    op.drop_constraint('fk_agents_production_deployment', 'agents', type_='foreignkey')
    op.drop_column('agents', 'production_deployment_id')

    # Drop deployments table
    op.drop_index('idx_deployments_sgp_deploy_id', table_name='deployments')
    op.drop_index('idx_deployments_agent_production', table_name='deployments')
    op.drop_index('idx_deployments_agent_id', table_name='deployments')
    op.drop_table('deployments')

    # Drop the enum type
    sa.Enum(name='deploymentstatus').drop(op.get_bind(), checkfirst=True)
