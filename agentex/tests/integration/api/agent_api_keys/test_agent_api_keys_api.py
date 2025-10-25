"""
Integration tests for agent API keys endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import hashlib
import hmac
import time

import pytest
import pytest_asyncio
from httpx import Request, Response
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.entities.agents import ACPType, AgentEntity
from src.utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentAPIKeysIntegration:
    """Integration tests for agent API keys endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for API key creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent",
            description="Test agent for integration testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_agent_api_key(self, isolated_repositories, test_agent):
        """Create a test API key for the test agent"""
        # Now create an API key for this agent
        agent_api_key_repo = isolated_repositories["agent_api_key_repository"]
        agent_api_key = AgentAPIKeyEntity(
            id=orm_id(),
            name="test-api-key",
            agent_id=test_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        return await agent_api_key_repo.create(agent_api_key)

    @pytest_asyncio.fixture
    async def test_agent_api_key_github(self, isolated_repositories, test_agent):
        """Create a test API key for the test agent"""
        # Now create an API key for this agent
        agent_api_key_repo = isolated_repositories["agent_api_key_repository"]
        agent_api_key = AgentAPIKeyEntity(
            id=orm_id(),
            name="test-github-repository",
            agent_id=test_agent.id,
            api_key_type=AgentAPIKeyType.GITHUB,
            api_key="test-api-key-value",
        )
        return await agent_api_key_repo.create(agent_api_key)

    @pytest_asyncio.fixture
    async def test_agent_api_key_slack(self, isolated_repositories, test_agent):
        """Create a test API key for the test agent"""
        # Now create an API key for this agent
        agent_api_key_repo = isolated_repositories["agent_api_key_repository"]
        agent_api_key = AgentAPIKeyEntity(
            id=orm_id(),
            name="test-api-app-id",
            agent_id=test_agent.id,
            api_key_type=AgentAPIKeyType.SLACK,
            api_key="test-api-key-value",
        )
        return await agent_api_key_repo.create(agent_api_key)

    async def test_invalid_create_api_key(self, isolated_client):
        """Test that creating an API key with invalid parameters returns 400"""
        response = await isolated_client.post(
            "/agent_api_keys",
            json={
                "name": "test-api-key",
            },
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Either 'agent_id' or 'agent_name' must be provided to create an agent api_key."
        )

        response = await isolated_client.post(
            "/agent_api_keys",
            json={
                "name": "test-api-key",
                "agent_id": "invalid-agent-id",
                "agent_name": "test-agent",
            },
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Only one of 'agent_id' or 'agent_name' should be provided to create an agent api_key."
        )

        response = await isolated_client.post(
            "/agent_api_keys",
            json={
                "agent_id": "invalid-agent-id",
                "name": "test-api-key",
            },
        )
        assert response.status_code == 404
        assert (
            response.json()["message"]
            == "Item with id 'invalid-agent-id' does not exist."
        )

    async def test_invalid_list_api_keys(self, isolated_client):
        """Test that listing API keys with invalid parameters returns 400"""
        response = await isolated_client.get(
            "/agent_api_keys",
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Either 'agent_id' or 'agent_name' must be provided to list agent api_keys."
        )

        response = await isolated_client.get(
            "/agent_api_keys",
            params={
                "agent_id": "invalid-agent-id",
                "agent_name": "test-agent",
            },
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Only one of 'agent_id' or 'agent_name' should be provided to list agent api_keys."
        )

        response = await isolated_client.get(
            "/agent_api_keys",
            params={
                "agent_id": "invalid-agent-id",
            },
        )
        assert response.status_code == 404
        assert (
            response.json()["message"]
            == "Item with id 'invalid-agent-id' does not exist."
        )

    async def test_invalid_get_api_key_by_name(self, isolated_client):
        """Test that listing API keys with invalid parameters returns 400"""
        response = await isolated_client.get(
            "/agent_api_keys/name/test-api-key",
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Either 'agent_id' or 'agent_name' must be provided to get an agent api_key."
        )

        response = await isolated_client.get(
            "/agent_api_keys/name/test-api-key",
            params={
                "agent_id": "invalid-agent-id",
                "agent_name": "test-agent",
            },
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Only one of 'agent_id' or 'agent_name' should be provided to get an agent api_key."
        )

        response = await isolated_client.get(
            "/agent_api_keys/name/test-api-key",
            params={
                "agent_id": "invalid-agent-id",
            },
        )
        assert response.status_code == 404
        assert (
            response.json()["message"]
            == "Item with id 'invalid-agent-id' does not exist."
        )

    async def test_invalid_delete_api_key_by_name(self, isolated_client):
        """Test that listing API keys with invalid parameters returns 400"""
        response = await isolated_client.delete(
            "/agent_api_keys/name/test-api-key",
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Either 'agent_id' or 'agent_name' must be provided to delete an agent api_key."
        )

        response = await isolated_client.delete(
            "/agent_api_keys/name/test-api-key",
            params={
                "agent_id": "invalid-agent-id",
                "agent_name": "test-agent",
            },
        )
        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "Only one of 'agent_id' or 'agent_name' should be provided to delete an agent api_key."
        )

        response = await isolated_client.delete(
            "/agent_api_keys/name/test-api-key",
            params={
                "agent_id": "invalid-agent-id",
            },
        )
        assert response.status_code == 404
        assert (
            response.json()["message"]
            == "Item with id 'invalid-agent-id' does not exist."
        )

    async def test_create_api_key(self, isolated_client, test_agent):
        """Test that creating an API key works correctly"""
        # Given - No existing agent API keys (verify with GET)
        initial_response = await isolated_client.get(
            "/agent_api_keys",
            params={"agent_id": test_agent.id},
        )
        assert initial_response.status_code == 200
        initial_agent_keys = initial_response.json()
        initial_count = len(initial_agent_keys)

        # When - Register new agent via API
        create_response = await isolated_client.post(
            "/agent_api_keys",
            json={
                "name": "test-api-key",
                "agent_id": test_agent.id,
            },
        )

        # Then - Validate POST response
        assert create_response.status_code == 200
        agent_api_key_data = create_response.json()
        assert agent_api_key_data["name"] == "test-api-key"
        assert agent_api_key_data["agent_id"] == test_agent.id
        assert agent_api_key_data["api_key_type"] == AgentAPIKeyType.EXTERNAL
        assert "id" in agent_api_key_data
        assert "api_key" in agent_api_key_data
        assert agent_api_key_data["created_at"] is not None

        # Verify count increased by one
        final_response = await isolated_client.get(
            "/agent_api_keys",
            params={"agent_id": test_agent.id},
        )
        assert final_response.status_code == 200
        final_agent_keys = final_response.json()
        final_count = len(final_agent_keys)
        assert final_count == initial_count + 1

    async def test_create_api_key_with_agent_name(self, isolated_client, test_agent):
        """Test that creating an API key works correctly"""
        # Given - No existing agent API keys (verify with GET)
        initial_response = await isolated_client.get(
            "/agent_api_keys",
            params={"agent_name": test_agent.name},
        )
        assert initial_response.status_code == 200
        initial_agent_keys = initial_response.json()
        initial_count = len(initial_agent_keys)

        # When - Register new agent via API
        create_response = await isolated_client.post(
            "/agent_api_keys",
            json={
                "name": "test-api-key",
                "agent_name": test_agent.name,
            },
        )

        # Then - Validate POST response
        assert create_response.status_code == 200
        agent_api_key_data = create_response.json()
        assert agent_api_key_data["name"] == "test-api-key"
        assert agent_api_key_data["agent_id"] == test_agent.id
        assert agent_api_key_data["api_key_type"] == AgentAPIKeyType.EXTERNAL
        assert "id" in agent_api_key_data
        assert "api_key" in agent_api_key_data
        assert agent_api_key_data["created_at"] is not None

        # Verify count increased by one
        final_response = await isolated_client.get(
            "/agent_api_keys",
            params={"agent_name": test_agent.name},
        )
        assert final_response.status_code == 200
        final_agent_keys = final_response.json()
        final_count = len(final_agent_keys)
        assert final_count == initial_count + 1

    async def test_get_api_key_returns_valid_data(
        self, isolated_client, test_agent_api_key
    ):
        """Test getting an API key by ID returns valid data"""
        # Given - Existing API key for the agent
        # When - Get the API key by ID
        response = await isolated_client.get(
            f"/agent_api_keys/{test_agent_api_key.id}",
        )

        # Then - Should return 200 with valid data
        assert response.status_code == 200
        retrieved_data = response.json()
        assert retrieved_data["id"] == test_agent_api_key.id
        assert retrieved_data["name"] == test_agent_api_key.name
        assert retrieved_data["agent_id"] == test_agent_api_key.agent_id
        assert retrieved_data["api_key_type"] == test_agent_api_key.api_key_type

    async def test_create_and_retrieve_api_keys(
        self, isolated_client, test_agent, num_keys=5
    ):
        """Test creating and retrieving an API key for an agent"""
        # Given - No existing agent API keys (verify with GET)
        initial_response = await isolated_client.get(
            "/agent_api_keys",
            params={"agent_id": test_agent.id},
        )
        assert initial_response.status_code == 200
        initial_agent_keys = initial_response.json()
        initial_count = len(initial_agent_keys)

        # When - Create several new API keys for the agent
        for i in range(num_keys):
            create_response = await isolated_client.post(
                "/agent_api_keys",
                json={
                    "name": f"test-api-key-{i}",
                    "agent_id": test_agent.id,
                },
            )
            # Then - Validate POST response
            assert create_response.status_code == 200

        # And - Verify keys appear in agent list
        list_response = await isolated_client.get(
            "/agent_api_keys",
            params={"agent_id": test_agent.id},
        )
        assert list_response.status_code == 200
        list_keys = list_response.json()
        assert len(list_keys) == initial_count + num_keys
        key_names = {key["name"] for key in list_keys}
        assert all(f"test-api-key-{i}" in key_names for i in range(num_keys))

        # And - Verify each key can be retrieved by name
        for i in range(num_keys):
            get_by_name_response = await isolated_client.get(
                f"/agent_api_keys/name/test-api-key-{i}",
                params={"agent_id": test_agent.id},
            )
            assert get_by_name_response.status_code == 200

    async def test_create_api_key_with_existing_name_returns_409(
        self,
        isolated_client,
        test_agent_api_key,
    ):
        """Test creating an API key with an existing name returns proper 409 error"""
        # Given - Existing API key for the agent
        existing_key = await isolated_client.get(
            f"/agent_api_keys/name/{test_agent_api_key.name}",
            params={"agent_id": test_agent_api_key.agent_id},
        )
        assert existing_key.status_code == 200
        # When - Attempt to create another API key with the same name
        response = await isolated_client.post(
            "/agent_api_keys",
            json={
                "name": test_agent_api_key.name,  # Same name as existing key
                "agent_id": test_agent_api_key.agent_id,
                "api_key": "new-api-key-value",
            },
        )

        # Then - Should return 409 with proper error message
        assert response.status_code == 409
        error_data = response.json()
        assert "already exists" in error_data["message"]

    async def test_get_api_key_non_existent_returns_404(
        self, isolated_client, test_agent
    ):
        """Test getting a non-existent API key returns proper 404"""
        # When - Get a non-existent API key
        response = await isolated_client.get(
            "/agent_api_keys/name/non-existent-api-key-name",
            params={"agent_id": test_agent.id},
        )

        # Then - Should return 404 with proper error message
        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["message"]

        response = await isolated_client.get(
            "/agent_api_keys/non-existent-api-key-id",
        )

        # Then - Should return 404 with proper error message
        assert response.status_code == 404
        error_data = response.json()
        assert "does not exist" in error_data["message"]

    async def test_delete_api_key_by_name(self, isolated_client, test_agent_api_key):
        """Test deleting an API key by name"""
        # Given - Existing API key for the agent
        existing_key = await isolated_client.get(
            f"/agent_api_keys/name/{test_agent_api_key.name}",
            params={"agent_id": test_agent_api_key.agent_id},
        )
        assert existing_key.status_code == 200

        # When - Delete the API key by name
        delete_response = await isolated_client.delete(
            f"/agent_api_keys/name/{test_agent_api_key.name}",
            params={"agent_id": test_agent_api_key.agent_id},
        )

        # Then - Should return 200 with success message
        assert delete_response.status_code == 200
        assert (
            delete_response.json()
            == f"Agent api_key '{test_agent_api_key.name}' deleted"
        )

        # And - Verify the key is no longer retrievable
        get_after_delete_response = await isolated_client.get(
            f"/agent_api_keys/name/{test_agent_api_key.name}",
            params={"agent_id": test_agent_api_key.agent_id},
        )
        assert get_after_delete_response.status_code == 404

    async def test_delete_api_key_by_id(self, isolated_client, test_agent_api_key):
        """Test deleting an API key by ID"""
        # Given - Existing API key for the agent
        existing_key = await isolated_client.get(
            f"/agent_api_keys/name/{test_agent_api_key.name}",
            params={"agent_id": test_agent_api_key.agent_id},
        )
        assert existing_key.status_code == 200

        # When - Delete the API key by ID
        delete_response = await isolated_client.delete(
            f"/agent_api_keys/{test_agent_api_key.id}",
        )

        # Then - Should return 200 with success message
        assert delete_response.status_code == 200
        assert (
            delete_response.json()
            == f"Agent API key with ID {test_agent_api_key.id} deleted"
        )

        # And - Verify the key is no longer retrievable
        get_after_delete_response = await isolated_client.get(
            f"/agent_api_keys/name/{test_agent_api_key.name}",
            params={"agent_id": test_agent_api_key.agent_id},
        )
        assert get_after_delete_response.status_code == 404

    async def test_forwarding_get_request(
        self,
        isolated_client,
        test_agent_api_key,
        isolated_api_key_http_client,
    ):
        # Given - An agent with an API key
        mock_request = Request(
            method="GET",
            url="http://example.com",
        )
        # This is the request object passed to mock client to simulate the forwarded request
        isolated_api_key_http_client.build_request.return_value = mock_request

        mock_response = {
            "message": "Forwarded request successfully",
        }
        isolated_api_key_http_client.send.return_value = Response(
            json=mock_response,
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

        # When - Forward a request to the agent
        forward_response = await isolated_client.get(
            "/agents/forward/name/test-agent/some/path?query=value",
            headers={"x-agent-api-key": "test-api-key-value"},
        )
        assert forward_response.status_code == 200
        assert forward_response.json() == mock_response

        # Then - Verify the request was forwarded correctly
        isolated_api_key_http_client.build_request.assert_called_once()
        call_args = isolated_api_key_http_client.build_request.call_args
        assert call_args[0][0] == "GET"  # Method should be GET
        assert (
            call_args[0][1] == "http://test-acp:8000/some/path?query=value"
        )  # URL should match agent's ACP URL

        isolated_api_key_http_client.send.assert_called_once()
        call_args = isolated_api_key_http_client.send.call_args
        assert call_args[0][0] == mock_request  # Request should match the one built
        assert call_args[1]["stream"] is False  # Should not be streaming response

    async def test_forwarding_post_request(
        self,
        isolated_client,
        test_agent_api_key,
        isolated_api_key_http_client,
    ):
        # Given - An agent with an API key
        mock_request = Request(
            method="POST",
            url="http://example.com",
        )
        # This is the request object passed to mock client to simulate the forwarded request
        isolated_api_key_http_client.build_request.return_value = mock_request

        mock_response = {
            "message": "Forwarded request successfully",
        }
        isolated_api_key_http_client.send.return_value = Response(
            json=mock_response,
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

        # When - Forward a request to the agent
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"key": "value"},
            headers={"x-agent-api-key": "test-api-key-value"},
        )
        assert forward_response.status_code == 200
        assert forward_response.json() == mock_response

        # Then - Verify the request was forwarded correctly
        isolated_api_key_http_client.build_request.assert_called_once()
        call_args = isolated_api_key_http_client.build_request.call_args
        assert call_args[0][0] == "POST"  # Method should be POST
        assert (
            call_args[0][1] == "http://test-acp:8000/some/path"
        )  # URL should match agent's ACP URL
        assert call_args[1]["content"] == b'{"key": "value"}'  # Body should match

        isolated_api_key_http_client.send.assert_called_once()
        call_args = isolated_api_key_http_client.send.call_args
        assert call_args[0][0] == mock_request  # Request should match the one built
        assert call_args[1]["stream"] is False  # Should not be streaming response

    async def test_forwarding_request_with_github_webhook(
        self,
        isolated_client,
        test_agent_api_key_github,
        isolated_api_key_http_client,
    ):
        """Test forwarding a request with a GitHub header"""
        # Given - An agent with an API key
        mock_request = Request(
            method="POST",
            url="http://example.com",
        )
        # This is the request object passed to mock client to simulate the forwarded request
        isolated_api_key_http_client.build_request.return_value = mock_request

        mock_response = {
            "message": "Forwarded request successfully",
        }
        isolated_api_key_http_client.send.return_value = Response(
            json=mock_response,
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

        # Test bad / missing payload
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            content=None,
            headers={
                "x-hub-signature-256": "test-github-signature",
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {"detail": "Empty payload in GitHub webhook."}

        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            content="invalid-json",
            headers={
                "x-hub-signature-256": "test-github-signature",
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "Failed to parse GitHub webhook payload as JSON."
        }

        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"key": "value"},
            headers={
                "x-hub-signature-256": "test-github-signature",
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "GitHub webhook payload missing repository info."
        }

        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"repository": {"owner": "name"}},
            headers={
                "x-hub-signature-256": "test-github-signature",
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "GitHub webhook payload missing repository name."
        }

        # Missing API Key
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"repository": {"full_name": "wrong-repository-name"}},
            headers={
                "x-hub-signature-256": "test-github-signature",
            },
        )
        assert forward_response.status_code == 404
        assert forward_response.json() == {
            "detail": "No API key found for GitHub repository wrong-repository-name."
        }

        # Bad GitHub signature
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            content=b'{"repository": {"full_name": "test-github-repository"}}',
            headers={
                "x-hub-signature-256": "test-github-signature",
            },
        )
        assert forward_response.status_code == 401
        assert forward_response.json() == {"detail": "Invalid GitHub webhook signature"}

        # Good GitHub signature
        payload_body = b'{"repository": {"full_name": "test-github-repository"}}'
        hash_object = hmac.new(
            test_agent_api_key_github.api_key.encode("utf-8"),
            msg=payload_body,
            digestmod=hashlib.sha256,
        )
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            content=payload_body,
            headers={
                "x-hub-signature-256": "sha256=" + hash_object.hexdigest(),
            },
        )
        assert forward_response.status_code == 200
        assert forward_response.json() == mock_response

    async def test_forwarding_request_with_slack(
        self,
        isolated_client,
        test_agent_api_key_slack,
        isolated_api_key_http_client,
    ):
        """Test forwarding a request with a slack header"""
        # Given - An agent with an API key
        mock_request = Request(
            method="POST",
            url="http://example.com",
        )
        # This is the request object passed to mock client to simulate the forwarded request
        isolated_api_key_http_client.build_request.return_value = mock_request

        mock_response = {
            "message": "Forwarded request successfully",
        }
        isolated_api_key_http_client.send.return_value = Response(
            json=mock_response,
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

        # Test bad JSON input
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            content="invalid-json",
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": "test-slack-request-timestamp",
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "Invalid Slack verification request."
        }

        # Test Slack Challenge response
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"challenge": "test-challenge"},
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": "test-slack-request-timestamp",
            },
        )
        assert forward_response.status_code == 200
        assert forward_response.content == b"test-challenge"

        # Test Slack webhook payload with bad timestamp
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"api_app_id": test_agent_api_key_slack.name},
            headers={
                "x-slack-signature": "test-slack-signature",
            },
        )
        assert forward_response.status_code == 401
        assert forward_response.json() == {
            "detail": "Missing X-Slack-Request-Timestamp header."
        }

        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"api_app_id": test_agent_api_key_slack.name},
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": "test-slack-request-timestamp",
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "Invalid X-Slack-Request-Timestamp header value."
        }

        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"api_app_id": test_agent_api_key_slack.name},
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": str(int(time.time() - 60 * 10)),
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "Slack webhook request has bad timestamp."
        }

        # API App ID
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"key": "value"},
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": str(int(time.time())),
            },
        )
        assert forward_response.status_code == 400
        assert forward_response.json() == {
            "detail": "Slack webhook payload missing API app ID."
        }

        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"api_app_id": "wrong-api-app-id"},
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": str(int(time.time())),
            },
        )
        assert forward_response.status_code == 404
        assert forward_response.json() == {
            "detail": "No API key found for Slack app wrong-api-app-id."
        }

        # Bad Slack signature
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"api_app_id": test_agent_api_key_slack.name},
            headers={
                "x-slack-signature": "test-slack-signature",
                "x-slack-request-timestamp": str(int(time.time())),
            },
        )
        assert forward_response.status_code == 401
        assert forward_response.json() == {"detail": "Invalid Slack webhook signature"}

        # Good Slack signature
        request_timestamp = int(time.time())
        payload_body = b'{"api_app_id": "test-api-app-id"}'
        hash_object = hmac.new(
            test_agent_api_key_slack.api_key.encode("utf-8"),
            msg=f"v0:{request_timestamp}:".encode() + payload_body,
            digestmod=hashlib.sha256,
        )
        forward_response = await isolated_client.post(
            "/agents/forward/name/test-agent/some/path",
            json={"api_app_id": test_agent_api_key_slack.name},
            headers={
                "x-slack-signature": "v0=" + hash_object.hexdigest(),
                "x-slack-request-timestamp": str(request_timestamp),
            },
        )
        assert forward_response.status_code == 200
        assert forward_response.json() == mock_response

    async def test_forwarding_request_with_wrong_agent_name(
        self,
        isolated_client,
        test_agent_api_key,
        isolated_api_key_http_client,
    ):
        """Test forwarding a request with a wrong agent name returns 404"""
        response = await isolated_client.get(
            "/agents/forward/name/wrong-agent-name/some/path",
            headers={"x-agent-api-key": "test-api-key-value"},
        )
        assert response.status_code == 404
        assert response.json() == {
            "detail": "Agent wrong-agent-name not found or has no ACP URL."
        }

    async def test_forwarding_request_without_auth(
        self, isolated_client, test_agent_api_key
    ):
        """Test forwarding a request without x-agent-api-key header returns 403"""
        response = await isolated_client.get(
            "/agents/forward/name/test-agent/some/path"
        )
        assert response.status_code == 403

    async def test_forwarding_request_with_invalid_api_key(
        self, isolated_client, test_agent_api_key
    ):
        """Test forwarding a request with an invalid API key returns 401"""
        response = await isolated_client.get(
            "/agents/forward/name/test-agent/some/path",
            headers={"x-agent-api-key": "invalid-api-key"},
        )
        assert response.status_code == 401
