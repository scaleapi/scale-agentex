"""The slack_socket_mode_apps table's guarantees, against a real Postgres."""

import pytest
from src.adapters.crud_store.exceptions import DuplicateItemError
from src.domain.entities.agent_api_keys import (
    AgentAPIKeyEntity,
    AgentAPIKeyType,
    SlackSocketModeAppEntity,
)
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.utils.ids import orm_id

SLACK_APP_ID = "A123"


async def _agent(repos, name: str) -> AgentEntity:
    return await repos["agent_repository"].create(
        AgentEntity(
            id=orm_id(),
            name=name,
            description="Socket Mode test agent",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
    )


async def _register(repos, agent: AgentEntity) -> AgentAPIKeyEntity:
    trigger = AgentAPIKeyEntity(
        id=orm_id(),
        name=SLACK_APP_ID,
        agent_id=agent.id,
        api_key_type=AgentAPIKeyType.SLACK,
        api_key="signing-secret",
    )
    return await repos["agent_api_key_repository"].create_with_slack_socket_mode_app(
        item=trigger,
        app=SlackSocketModeAppEntity(
            id=orm_id(),
            agent_api_key_id=trigger.id,
            agent_id=agent.id,
            slack_app_id=SLACK_APP_ID,
            app_token_encrypted="ciphertext",
            forward_path="slack/events",
        ),
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestSlackSocketModeApps:
    async def test_one_live_agent_per_slack_app(self, isolated_repositories):
        repos = isolated_repositories
        key_repo = repos["agent_api_key_repository"]
        first = await _agent(repos, "first-agent")
        second = await _agent(repos, "second-agent")
        await _register(repos, first)

        with pytest.raises(DuplicateItemError):
            await _register(repos, second)
        # The failed registration must not leave its trigger row behind.
        assert not await key_repo.get_by_agent_id_and_name(
            agent_id=second.id, name=SLACK_APP_ID, api_key_type=AgentAPIKeyType.SLACK
        )

        # Deleting an agent keeps its keys, so its stale row must not hold the app.
        await repos["agent_repository"].update(
            first.model_copy(update={"status": AgentStatus.DELETED})
        )
        trigger = await _register(repos, second)

        served = await key_repo.list_slack_socket_mode_apps()
        assert [(t.id, app.agent_id) for t, app in served] == [(trigger.id, second.id)]

    async def test_deleting_the_trigger_removes_the_app(self, isolated_repositories):
        repos = isolated_repositories
        key_repo = repos["agent_api_key_repository"]
        trigger = await _register(repos, await _agent(repos, "socket-agent"))

        await key_repo.delete(trigger.id)

        assert await key_repo.list_slack_socket_mode_apps() == []
