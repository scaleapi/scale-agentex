"""The slack_socket_mode_apps table and its endpoints, against a real Postgres."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from src.adapters.crud_store.exceptions import DuplicateItemError
from src.domain.entities.agent_api_keys import (
    AgentAPIKeyEntity,
    AgentAPIKeyType,
    SlackSocketModeAppEntity,
)
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.services import slack_socket_mode_bridge
from src.utils import credential_encryption
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


@pytest_asyncio.fixture
async def socket_mode_api(isolated_client, monkeypatch):
    """The HTTP API, with an encryption key and Slack's app-id check answered locally."""
    credential_encryption.reset_cache()
    monkeypatch.setenv(credential_encryption.ENV_KEY, Fernet.generate_key().decode())
    monkeypatch.setattr(
        slack_socket_mode_bridge,
        "read_slack_app_id",
        AsyncMock(return_value=SLACK_APP_ID),
    )
    yield isolated_client
    credential_encryption.reset_cache()


async def _http_trigger(repos, agent: AgentEntity, source=AgentAPIKeyType.SLACK):
    return await repos["agent_api_key_repository"].create(
        AgentAPIKeyEntity(
            id=orm_id(),
            name=SLACK_APP_ID,
            agent_id=agent.id,
            api_key_type=source,
            api_key="signing-secret",
        )
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestSlackSocketModeEndpoints:
    async def test_put_turns_socket_mode_on_then_replaces_it(
        self, socket_mode_api, isolated_repositories
    ):
        repos = isolated_repositories
        trigger = await _http_trigger(repos, await _agent(repos, "socket-agent"))
        url = f"/agent_api_keys/{trigger.id}/slack_socket_mode"

        first = await socket_mode_api.put(
            url, json={"app_token": "xapp-1", "forward_path": "slack/events"}
        )
        # The trigger already serving the app must not conflict with itself.
        second = await socket_mode_api.put(
            url, json={"app_token": "xapp-2", "forward_path": "/slack/v2"}
        )

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        served = await repos["agent_api_key_repository"].list_slack_socket_mode_apps()
        assert [(t.id, app.forward_path) for t, app in served] == [
            (trigger.id, "slack/v2")
        ]

    async def test_put_conflicts_with_another_trigger_for_the_app(
        self, socket_mode_api, isolated_repositories
    ):
        repos = isolated_repositories
        await _register(repos, await _agent(repos, "first-agent"))
        other = await _http_trigger(repos, await _agent(repos, "second-agent"))

        response = await socket_mode_api.put(
            f"/agent_api_keys/{other.id}/slack_socket_mode",
            json={"app_token": "xapp-1", "forward_path": "slack/events"},
        )

        assert response.status_code == 409, response.text

    async def test_put_refuses_a_trigger_that_is_not_slack(
        self, socket_mode_api, isolated_repositories
    ):
        repos = isolated_repositories
        trigger = await _http_trigger(
            repos, await _agent(repos, "github-agent"), AgentAPIKeyType.GITHUB
        )

        response = await socket_mode_api.put(
            f"/agent_api_keys/{trigger.id}/slack_socket_mode",
            json={"app_token": "xapp-1", "forward_path": "slack/events"},
        )

        assert response.status_code == 400, response.text

    async def test_delete_turns_socket_mode_off_and_keeps_the_trigger(
        self, socket_mode_api, isolated_repositories
    ):
        repos = isolated_repositories
        trigger = await _register(repos, await _agent(repos, "socket-agent"))
        url = f"/agent_api_keys/{trigger.id}/slack_socket_mode"

        assert (await socket_mode_api.delete(url)).status_code == 200
        assert (await socket_mode_api.delete(url)).status_code == 404

        key_repo = repos["agent_api_key_repository"]
        assert await key_repo.list_slack_socket_mode_apps() == []
        assert (
            await socket_mode_api.get(f"/agent_api_keys/{trigger.id}")
        ).status_code == 200
