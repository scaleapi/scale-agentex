"""slack socket mode apps

Revision ID: f3a5c7e9b1d2
Revises: e2f4a6c8b0d1
Create Date: 2026-11-16 12:00:00.000000

Creates ``slack_socket_mode_apps``: one row per Slack app whose events agentex
receives over Socket Mode, attached to the app's Slack webhook trigger in
``agent_api_keys``. The table is new and empty, so its constraints build without
scanning anything; the foreign key briefly locks ``agent_api_keys`` and does not scan
it. IF NOT EXISTS makes a re-run a no-op.
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
        """
        CREATE TABLE IF NOT EXISTS slack_socket_mode_apps (
            id VARCHAR NOT NULL PRIMARY KEY,
            agent_api_key_id VARCHAR NOT NULL,
            agent_id VARCHAR(64) NOT NULL,
            slack_app_id VARCHAR(256) NOT NULL,
            app_token_encrypted VARCHAR NOT NULL,
            forward_path VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            CONSTRAINT uq_slack_socket_mode_apps_slack_app_id UNIQUE (slack_app_id),
            CONSTRAINT uq_slack_socket_mode_apps_agent_api_key
                UNIQUE (agent_api_key_id, agent_id),
            CONSTRAINT fk_slack_socket_mode_apps_agent_api_key
                FOREIGN KEY (agent_api_key_id, agent_id)
                REFERENCES agent_api_keys (id, agent_id) ON DELETE CASCADE
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS slack_socket_mode_apps;")
