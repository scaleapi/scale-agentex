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
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_deployments_agent_id', 'deployments', ['agent_id'], unique=False)
    op.create_index('idx_deployments_agent_production', 'deployments', ['agent_id', 'is_production'], unique=False)
    op.create_index('idx_deployments_sgp_deploy_id', 'deployments', ['sgp_deploy_id'], unique=False)

    # 2. Add production_deployment_id to agents table
    op.add_column('agents', sa.Column('production_deployment_id', sa.String(), nullable=True))
    op.create_foreign_key('fk_agents_production_deployment', 'agents', 'deployments', ['production_deployment_id'], ['id'])

    # 3. Migrate deployment_history records into deployments.
    #    For each agent, the most recent deployment_history record becomes the production deployment.
    op.execute("""
        WITH ranked AS (
            SELECT
                dh.id,
                dh.agent_id,
                dh.commit_hash,
                dh.branch_name,
                dh.author_name,
                dh.author_email,
                dh.build_timestamp,
                dh.deployment_timestamp,
                a.acp_url AS agent_acp_url,
                a.docker_image AS agent_docker_image,
                ROW_NUMBER() OVER (PARTITION BY dh.agent_id ORDER BY dh.deployment_timestamp DESC) AS rn
            FROM deployment_history dh
            JOIN agents a ON a.id = dh.agent_id
            WHERE dh.agent_id IS NOT NULL
        )
        INSERT INTO deployments (id, agent_id, docker_image, commit_hash, branch_name, author_name, author_email, build_timestamp, status, acp_url, is_production, created_at, promoted_at)
        SELECT
            id,
            agent_id,
            COALESCE(agent_docker_image, 'unknown'),
            commit_hash,
            branch_name,
            author_name,
            author_email,
            build_timestamp,
            'Ready',
            CASE WHEN rn = 1 THEN agent_acp_url ELSE NULL END,
            CASE WHEN rn = 1 THEN true ELSE false END,
            deployment_timestamp,
            CASE WHEN rn = 1 THEN deployment_timestamp ELSE NULL END
        FROM ranked
    """)

    # 4. Set production_deployment_id on agents that have a production deployment
    op.execute("""
        UPDATE agents
        SET production_deployment_id = d.id
        FROM deployments d
        WHERE d.agent_id = agents.id AND d.is_production = true
    """)

    # 5. Make deployment_history.agent_id nullable (deprecated table)
    op.alter_column('deployment_history', 'agent_id',
               existing_type=sa.VARCHAR(length=64),
               nullable=True)


def downgrade() -> None:
    op.alter_column('deployment_history', 'agent_id',
               existing_type=sa.VARCHAR(length=64),
               nullable=False)

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
