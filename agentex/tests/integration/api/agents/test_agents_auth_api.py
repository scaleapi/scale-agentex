"""
Integration tests for agent endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from src.api.schemas.authorization_types import AgentexResourceType

# from src.api.schemas.authorized_operation_type import AuthorizedOperationType
from src.domain.entities.agents import ACPType, AgentEntity

MOCK_PRINCIPAL_CONTEXT = {
    "account_id": "test-account-id",
    "user_id": "test-user-id",
}


async def _mock_post_with_error_handling(
    base_url: str = "http://test.com",
    path: str = "/test",
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    if path == "/v1/authn":
        return MOCK_PRINCIPAL_CONTEXT
    elif path == "/v1/authz/search":
        return {"items": ["agent-id-1"]}
    elif path == "/v1/authz/check":
        return {"allowed": True}
    elif path == "/v1/authz/grant":
        return {"success": True}
    elif path == "/v1/authz/revoke":
        return {"success": True}
    elif path == "/v1/authz/register":
        return {"success": True}
    elif path == "/v1/authz/deregister":
        return {"success": True}
    raise Exception(f"Unknown path: {path}")


@pytest.mark.integration
class TestAgentsAuthAPIIntegration:
    """Integration tests for agent endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_authorized_agent(self, isolated_repositories):
        """Create a test agent for API key creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id="agent-id-1",
            name="test-authorized-agent",
            description="Test agent for integration testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_unauthorized_agent(self, isolated_repositories):
        """Create a test agent for API key creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id="agent-id-2",
            name="test-unauthorized-agent",
            description="Test agent for integration testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_with_error_handling,
    )
    async def test_agent_list(
        self,
        post_with_error_handling_mock,
        is_enabled_mock,
        is_enabled_authorization_mock,
        isolated_client,
        test_authorized_agent,
        test_unauthorized_agent,
    ):
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        initial_agents = response.json()
        # Only authorized agent should be returned
        assert len(initial_agents) == 1
        assert initial_agents[0]["id"] == test_authorized_agent.id

        assert post_with_error_handling_mock.call_count == 2  # 1 for authn, 1 for authz
        assert post_with_error_handling_mock.call_args_list[0][0][1] == "/v1/authn"
        assert (
            post_with_error_handling_mock.call_args_list[1][0][1] == "/v1/authz/search"
        )
        authz_data = post_with_error_handling_mock.call_args_list[1][1]["json"]
        assert authz_data["filter_resource"] == AgentexResourceType.agent
        assert authz_data["filter_operation"] == "read"
        assert authz_data["principal"] == MOCK_PRINCIPAL_CONTEXT

        # Second call will use auth cache and not make a request to the authn service
        post_with_error_handling_mock.reset_mock()
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        initial_agents = response.json()
        # Only authorized agent should be returned
        assert len(initial_agents) == 1
        assert initial_agents[0]["id"] == test_authorized_agent.id

        # No request to the authz service thanks to auth cache
        assert post_with_error_handling_mock.call_count == 1
        assert (
            post_with_error_handling_mock.call_args_list[0][0][1] == "/v1/authz/search"
        )

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_with_error_handling,
    )
    async def test_agent_check(
        self,
        post_with_error_handling_mock,
        is_enabled_mock,
        is_enabled_authorization_mock,
        isolated_client,
        test_authorized_agent,
    ):
        response = await isolated_client.get("/agents/name/test-authorized-agent")
        assert response.status_code == 200
        agent = response.json()
        assert agent["id"] == test_authorized_agent.id

        # First call will make a request to the authn service and the authz service
        assert post_with_error_handling_mock.call_count == 2
        assert post_with_error_handling_mock.call_args_list[0][0][1] == "/v1/authn"
        assert (
            post_with_error_handling_mock.call_args_list[1][0][1] == "/v1/authz/check"
        )
        authz_data = post_with_error_handling_mock.call_args_list[1][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.agent.value
        assert authz_data["resource"]["selector"] == test_authorized_agent.id
        assert authz_data["operation"] == "read"
        assert authz_data["principal"] == MOCK_PRINCIPAL_CONTEXT

        # Second call still uses the authn cache, but authorization checks go
        # directly to Spark so share/revoke changes are visible immediately.
        post_with_error_handling_mock.reset_mock()
        response = await isolated_client.get("/agents/name/test-authorized-agent")
        assert response.status_code == 200
        agent = response.json()
        assert agent["id"] == test_authorized_agent.id

        assert post_with_error_handling_mock.call_count == 1
        assert (
            post_with_error_handling_mock.call_args_list[0][0][1] == "/v1/authz/check"
        )

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_with_error_handling,
    )
    async def test_agent_register_skips_authz_and_delete_gates_legacy_authz(
        self,
        post_with_error_handling_mock,
        is_enabled_mock,
        is_enabled_authorization_mock,
        isolated_client,
    ):
        def _payloads(path: str):
            return [
                call[1]["json"]
                for call in post_with_error_handling_mock.call_args_list
                if call[0][1] == path
            ]

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-agent",
                "description": "Test agent for integration testing",
                "acp_url": "http://test-acp:8000",
                "acp_type": "sync",
            },
        )
        assert response.status_code == 200
        agent = response.json()

        # /agents/register is whitelisted: deployed pods self-register on
        # startup without a principal, so register does not gate on `create`
        # or write an ownership grant -- the agent is already owned from build
        # time (register-build runs first). Forwarding a None principal here
        # previously 422'd and crash-looped the pod.
        assert _payloads("/v1/authz/check") == []
        assert _payloads("/v1/authz/grant") == []

        post_with_error_handling_mock.reset_mock()
        response = await isolated_client.delete("/agents/name/test-agent")
        assert response.status_code == 200

        delete_checks = _payloads("/v1/authz/check")
        assert len(delete_checks) == 1
        assert delete_checks[0]["resource"]["type"] == AgentexResourceType.agent.value
        assert delete_checks[0]["resource"]["selector"] == agent["id"]
        assert delete_checks[0]["operation"] == "delete"
        assert delete_checks[0]["principal"] == MOCK_PRINCIPAL_CONTEXT

        agent_revokes = [
            payload
            for payload in _payloads("/v1/authz/revoke")
            if payload["resource"]["type"] == AgentexResourceType.agent.value
        ]
        assert len(agent_revokes) == 1
        assert agent_revokes[0]["resource"]["selector"] == agent["id"]
        assert agent_revokes[0]["operation"] == "delete"
