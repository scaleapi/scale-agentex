"""
Integration tests for ACPType backwards compatibility.
Tests the full HTTP API with legacy "agentic" agents.
"""

import pytest


@pytest.mark.integration
class TestACPTypeBackwardsCompatibilityIntegration:
    """Integration tests ensuring legacy AGENTIC agents work via API"""

    @pytest.mark.asyncio
    async def test_register_agent_with_agentic_type(self, isolated_client):
        """Test that we can register an agent with acp_type='agentic'"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "legacy-agentic-agent",
                "description": "A legacy agent using agentic type",
                "acp_url": "http://legacy-acp-server:8000",
                "acp_type": "agentic",
            },
        )

        assert response.status_code == 200
        agent_data = response.json()
        assert agent_data["name"] == "legacy-agentic-agent"
        assert agent_data["acp_type"] == "agentic"
        assert agent_data["id"] is not None
        assert "agent_api_key" in agent_data

    @pytest.mark.asyncio
    async def test_register_agent_with_async_type(self, isolated_client):
        """Test that we can register an agent with acp_type='async'"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "new-async-agent",
                "description": "A new agent using async type",
                "acp_url": "http://async-acp-server:8000",
                "acp_type": "async",
            },
        )

        assert response.status_code == 200
        agent_data = response.json()
        assert agent_data["name"] == "new-async-agent"
        assert agent_data["acp_type"] == "async"
        assert agent_data["id"] is not None
        assert "agent_api_key" in agent_data

    @pytest.mark.asyncio
    async def test_retrieve_agentic_agent_preserves_type(self, isolated_client):
        """Test that AGENTIC agents return 'agentic' in API responses (not converted)"""
        # Register an agentic agent
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-agentic-retrieval",
                "description": "Test retrieval of agentic type",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
            },
        )
        assert register_response.status_code == 200
        agent_id = register_response.json()["id"]

        # Retrieve by ID
        get_response = await isolated_client.get(f"/agents/{agent_id}")
        assert get_response.status_code == 200
        agent_data = get_response.json()
        assert (
            agent_data["acp_type"] == "agentic"
        ), "API should return 'agentic' for legacy agents, not convert to 'async'"

        # Retrieve by name
        get_by_name_response = await isolated_client.get(
            "/agents/name/test-agentic-retrieval"
        )
        assert get_by_name_response.status_code == 200
        agent_by_name = get_by_name_response.json()
        assert agent_by_name["acp_type"] == "agentic"

    @pytest.mark.asyncio
    async def test_list_agents_shows_both_agentic_and_async(self, isolated_client):
        """Test that listing agents shows both agentic and async types correctly"""
        # Register an agentic agent
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "list-test-agentic",
                "description": "Agentic agent for list test",
                "acp_url": "http://test1:8000",
                "acp_type": "agentic",
            },
        )

        # Register an async agent
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "list-test-async",
                "description": "Async agent for list test",
                "acp_url": "http://test2:8000",
                "acp_type": "async",
            },
        )

        # List all agents
        list_response = await isolated_client.get("/agents")
        assert list_response.status_code == 200
        agents = list_response.json()

        # Find our test agents
        agentic_agent = next(
            (a for a in agents if a["name"] == "list-test-agentic"), None
        )
        async_agent = next((a for a in agents if a["name"] == "list-test-async"), None)

        assert agentic_agent is not None
        assert agentic_agent["acp_type"] == "agentic"

        assert async_agent is not None
        assert async_agent["acp_type"] == "async"

    @pytest.mark.asyncio
    async def test_update_agent_from_agentic_to_async(self, isolated_client):
        """Test that we can update an agent from agentic to async type"""
        # Register an agentic agent
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "upgrade-test-agent",
                "description": "Agent to be upgraded",
                "acp_url": "http://test:8000",
                "acp_type": "agentic",
            },
        )
        assert register_response.status_code == 200
        agent_id = register_response.json()["id"]

        # Update to async type
        update_response = await isolated_client.post(
            "/agents/register",
            json={
                "agent_id": agent_id,
                "name": "upgrade-test-agent",
                "description": "Agent upgraded to async",
                "acp_url": "http://test:8000",
                "acp_type": "async",
            },
        )
        assert update_response.status_code == 200
        updated_agent = update_response.json()
        assert updated_agent["id"] == agent_id
        assert updated_agent["acp_type"] == "async"

        # Verify via GET
        get_response = await isolated_client.get(f"/agents/{agent_id}")
        assert get_response.status_code == 200
        assert get_response.json()["acp_type"] == "async"

    @pytest.mark.asyncio
    async def test_update_agent_from_async_to_agentic(self, isolated_client):
        """Test that we can update an agent from async to agentic type (for flexibility)"""
        # Register an async agent
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "downgrade-test-agent",
                "description": "Agent to be changed to agentic",
                "acp_url": "http://test:8000",
                "acp_type": "async",
            },
        )
        assert register_response.status_code == 200
        agent_id = register_response.json()["id"]

        # Update to agentic type
        update_response = await isolated_client.post(
            "/agents/register",
            json={
                "agent_id": agent_id,
                "name": "downgrade-test-agent",
                "description": "Agent changed to agentic",
                "acp_url": "http://test:8000",
                "acp_type": "agentic",
            },
        )
        assert update_response.status_code == 200
        updated_agent = update_response.json()
        assert updated_agent["id"] == agent_id
        assert updated_agent["acp_type"] == "agentic"

    @pytest.mark.asyncio
    async def test_invalid_acp_type_rejected(self, isolated_client):
        """Test that invalid acp_type values are rejected"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "invalid-type-agent",
                "description": "Agent with invalid type",
                "acp_url": "http://test:8000",
                "acp_type": "invalid_type",
            },
        )

        # Should return 422 Unprocessable Entity for invalid enum value
        assert response.status_code == 422
