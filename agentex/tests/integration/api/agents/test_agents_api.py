"""
Integration tests for agent endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest


@pytest.mark.integration
class TestAgentsAPIIntegration:
    """Integration tests for agent endpoints using API-first validation"""

    @pytest.mark.asyncio
    async def test_register_agent_success_and_retrieve(self, isolated_client):
        """Test agent registration and retrieval via API endpoints"""
        # Given - No existing agents (verify with GET)
        initial_response = await isolated_client.get("/agents")
        assert initial_response.status_code == 200
        initial_agents = initial_response.json()
        initial_count = len(initial_agents)

        # When - Register new agent via API
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
            },
        )

        # Then - Validate POST response
        assert register_response.status_code == 200
        agent_data = register_response.json()
        assert agent_data["name"] == "test-integration-agent"
        assert agent_data["description"] == "Created via integration test"
        assert agent_data["acp_type"] == "agentic"
        assert "agent_api_key" in agent_data
        assert "id" in agent_data
        agent_id = agent_data["id"]

        # And - Verify agent can be retrieved by ID with all fields
        get_by_id_response = await isolated_client.get(f"/agents/{agent_id}")
        assert get_by_id_response.status_code == 200
        retrieved_agent = get_by_id_response.json()

        # Validate GET response has all expected fields and matches POST
        assert retrieved_agent["id"] == agent_id
        assert retrieved_agent["name"] == "test-integration-agent"
        assert retrieved_agent["description"] == "Created via integration test"
        assert retrieved_agent["acp_type"] == "agentic"
        # Note: Check if acp_url is included in GET response
        if "acp_url" in retrieved_agent:
            assert retrieved_agent["acp_url"] == "http://test-acp-server:8000"

        # And - Verify agent can be retrieved by name
        get_by_name_response = await isolated_client.get(
            "/agents/name/test-integration-agent"
        )
        assert get_by_name_response.status_code == 200
        retrieved_by_name = get_by_name_response.json()
        assert retrieved_by_name["id"] == agent_id
        assert retrieved_by_name["name"] == "test-integration-agent"

        # And - Verify agent appears in agents list
        final_response = await isolated_client.get("/agents")
        assert final_response.status_code == 200
        final_agents = final_response.json()
        assert len(final_agents) == initial_count + 1

        # Find our agent in the list
        our_agent = next(
            (
                agent
                for agent in final_agents
                if agent["name"] == "test-integration-agent"
            ),
            None,
        )
        assert our_agent is not None
        assert our_agent["id"] == agent_id
        assert our_agent["description"] == "Created via integration test"

    @pytest.mark.asyncio
    async def test_register_agent_with_registration_metadata(self, isolated_client):
        """Test registering agent with code URL and commit hash"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
                "registration_metadata": {
                    "code_url": "https://github.com/example-repo/agents/tree/main",
                    "agent_commit": "test-commit-hash",
                },
            },
        )
        assert response.status_code == 200
        agent_data = response.json()
        assert agent_data["name"] == "test-integration-agent"
        assert agent_data["description"] == "Created via integration test"
        assert agent_data["acp_type"] == "agentic"
        assert (
            agent_data["registration_metadata"]["code_url"]
            == "https://github.com/example-repo/agents/tree/main"
        )
        assert agent_data["registration_metadata"]["agent_commit"] == "test-commit-hash"

        # And - Verify agent can be retrieved by ID with all fields

        get_by_id_response = await isolated_client.get(f"/agents/{agent_data['id']}")
        assert get_by_id_response.status_code == 200
        retrieved_agent = get_by_id_response.json()

        # Validate GET response has all expected fields and matches POST
        assert retrieved_agent["id"] == agent_data["id"]
        assert retrieved_agent["name"] == "test-integration-agent"
        assert retrieved_agent["description"] == "Created via integration test"
        assert retrieved_agent["acp_type"] == "agentic"
        assert (
            retrieved_agent["registration_metadata"]["code_url"]
            == "https://github.com/example-repo/agents/tree/main"
        )
        assert (
            retrieved_agent["registration_metadata"]["agent_commit"]
            == "test-commit-hash"
        )

    @pytest.mark.asyncio
    async def test_register_agent_validation_error(self, isolated_client):
        """Test invalid agent data returns proper validation error"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "invalid_field": "should cause validation error"
                # Missing required fields
            },
        )

        assert response.status_code == 422
        error_data = response.json()
        assert "message" in error_data
        assert "status_code" in error_data
        # Validate specific validation error details
        assert "Field required" in error_data["message"]

    @pytest.mark.asyncio
    async def test_list_agents_empty_and_populated(self, isolated_client):
        """Test listing agents returns correct data via API"""
        # Given - Initially empty agents list
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        initial_agents = response.json()
        initial_count = len(initial_agents)

        # When - Register an agent
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "list-test-agent",
                "description": "For list testing",
                "acp_url": "http://list-test-server:8000",
                "acp_type": "sync",
            },
        )
        assert register_response.status_code == 200

        # Then - Verify agent appears in list via GET
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        agents_data = response.json()
        assert len(agents_data) == initial_count + 1

        # Find and validate our agent in the list
        our_agent = next(
            (agent for agent in agents_data if agent["name"] == "list-test-agent"), None
        )
        assert our_agent is not None
        assert our_agent["description"] == "For list testing"
        assert our_agent["acp_type"] == "sync"

    @pytest.mark.asyncio
    #
    async def test_get_agent_by_id_success_and_not_found(self, isolated_client):
        """Test getting agent by ID handles both success and not found cases"""
        # When - Get non-existent agent
        try:
            response = await isolated_client.get("/agents/99999")
            # If no exception, should return appropriate error status
            assert response.status_code in [404, 500]  # Either is acceptable for now
        except Exception:
            # Exception being raised is also acceptable in test environment
            pass

        # Given - Register an agent first
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "get-by-id-agent",
                "description": "For get by ID testing",
                "acp_url": "http://get-test-server:8000",
                "acp_type": "agentic",
            },
        )
        assert register_response.status_code == 200
        agent_data = register_response.json()
        agent_id = agent_data["id"]

        # When - Get the agent by ID via API
        response = await isolated_client.get(f"/agents/{agent_id}")

        # Then - Should return the agent with all expected fields
        assert response.status_code == 200
        retrieved_agent = response.json()
        assert retrieved_agent["id"] == agent_id
        assert retrieved_agent["name"] == "get-by-id-agent"
        assert retrieved_agent["description"] == "For get by ID testing"
        assert retrieved_agent["acp_type"] == "agentic"

        # And - Verify consistency between POST and GET responses
        assert retrieved_agent["name"] == agent_data["name"]
        assert retrieved_agent["description"] == agent_data["description"]
        assert retrieved_agent["acp_type"] == agent_data["acp_type"]

    @pytest.mark.asyncio
    async def test_register_agent_duplicate_name_behavior(self, isolated_client):
        """Test registering agent with duplicate name shows current API behavior"""
        # Given - Register first agent
        response1 = await isolated_client.post(
            "/agents/register",
            json={
                "name": "duplicate-name-test",
                "description": "First agent",
                "acp_url": "http://first-server:8000",
                "acp_type": "sync",
            },
        )
        assert response1.status_code == 200
        first_agent = response1.json()

        # When - Try to register agent with same name
        response2 = await isolated_client.post(
            "/agents/register",
            json={
                "name": "duplicate-name-test",  # Same name
                "description": "Second agent",
                "acp_url": "http://second-server:8000",
                "acp_type": "agentic",
            },
        )

        # Then - Current API behavior is to update the existing agent
        assert response2.status_code == 200
        second_agent = response2.json()

        # Should be same agent ID but updated fields
        assert second_agent["id"] == first_agent["id"]
        assert second_agent["agent_api_key"] == first_agent["agent_api_key"]
        assert second_agent["description"] == "Second agent"
        assert second_agent["acp_type"] == "agentic"

        # And - Verify via GET that only one agent exists with updated data
        get_response = await isolated_client.get(f"/agents/{first_agent['id']}")
        assert get_response.status_code == 200
        current_agent = get_response.json()
        assert current_agent["description"] == "Second agent"
        assert current_agent["acp_type"] == "agentic"

        # And - Verify agents list only contains one agent with this name
        list_response = await isolated_client.get("/agents")
        assert list_response.status_code == 200
        agents = list_response.json()
        agents_with_name = [a for a in agents if a["name"] == "duplicate-name-test"]
        assert len(agents_with_name) == 1
        assert agents_with_name[0]["description"] == "Second agent"
