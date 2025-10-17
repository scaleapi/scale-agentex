"""
Integration tests for agent CRUD operations.
Tests basic Create, Read, Update, Delete operations via API endpoints.
"""

import pytest


@pytest.mark.integration
class TestAgentsCRUD:
    """
    Integration tests for agent CRUD operations using API-first validation.
    Each test gets completely isolated databases and focuses on API behavior.
    """

    @pytest.mark.asyncio
    async def test_health_endpoints(self, isolated_client):
        """Test health endpoints work with isolated app"""
        response = await isolated_client.get("/healthcheck")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_register_agent_basic(self, isolated_client, test_data_factory):
        """Test basic agent registration via API"""
        agent_data = test_data_factory["create_agent_data"]()

        response = await isolated_client.post("/agents/register", json=agent_data)

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == agent_data["name"]
        assert response_data["description"] == agent_data["description"]
        assert response_data["acp_type"] == agent_data["acp_type"]
        assert "id" in response_data
        assert "status" in response_data

    @pytest.mark.asyncio
    async def test_register_multiple_agents(self, isolated_client, test_data_factory):
        """Test registering multiple agents in same test session"""
        # Create multiple agents
        agent1_data = test_data_factory["create_agent_data"]("agent1")
        agent2_data = test_data_factory["create_agent_data"]("agent2")

        # Register first agent
        response1 = await isolated_client.post("/agents/register", json=agent1_data)
        assert response1.status_code == 200
        agent1 = response1.json()

        # Register second agent
        response2 = await isolated_client.post("/agents/register", json=agent2_data)
        assert response2.status_code == 200
        agent2 = response2.json()

        # Both agents should exist and be different
        assert agent1["id"] != agent2["id"]
        assert agent1["name"] != agent2["name"]

        # List all agents - should see both via API
        list_response = await isolated_client.get("/agents")
        assert list_response.status_code == 200
        agents = list_response.json()
        assert len(agents) == 2

        agent_names = {agent["name"] for agent in agents}
        assert agent1_data["name"] in agent_names
        assert agent2_data["name"] in agent_names

    @pytest.mark.asyncio
    # #
    async def test_get_agent_by_id(self, isolated_client, test_data_factory):
        """Test retrieving agent by ID"""
        # First register an agent
        agent_data = test_data_factory["create_agent_data"]()
        create_response = await isolated_client.post(
            "/agents/register", json=agent_data
        )
        assert create_response.status_code == 200
        created_agent = create_response.json()

        # Get agent by ID
        get_response = await isolated_client.get(f"/agents/{created_agent['id']}")
        assert get_response.status_code == 200
        retrieved_agent = get_response.json()

        # Should be the same agent
        assert retrieved_agent["id"] == created_agent["id"]
        assert retrieved_agent["name"] == agent_data["name"]
        assert retrieved_agent["description"] == agent_data["description"]

    @pytest.mark.asyncio
    # #
    async def test_get_agent_by_name(self, isolated_client, test_data_factory):
        """Test retrieving agent by name"""
        # Register an agent
        agent_data = test_data_factory["create_agent_data"]()
        create_response = await isolated_client.post(
            "/agents/register", json=agent_data
        )
        assert create_response.status_code == 200
        created_agent = create_response.json()

        # Get agent by name
        get_response = await isolated_client.get(f"/agents/name/{agent_data['name']}")
        assert get_response.status_code == 200
        retrieved_agent = get_response.json()

        # Should be the same agent
        assert retrieved_agent["id"] == created_agent["id"]
        assert retrieved_agent["name"] == agent_data["name"]

    @pytest.mark.asyncio
    async def test_agent_isolation_between_tests(
        self, isolated_client, test_data_factory
    ):
        """
        Test that demonstrates perfect isolation - this test won't see agents
        from other tests even if they run in parallel
        """
        # This test starts with a clean database
        list_response = await isolated_client.get("/agents")
        assert list_response.status_code == 200
        agents = list_response.json()
        assert len(agents) == 0  # Should be empty - complete isolation!

        # Register an agent specific to this test
        agent_data = test_data_factory["create_agent_data"]("isolated-agent")
        create_response = await isolated_client.post(
            "/agents/register", json=agent_data
        )
        assert create_response.status_code == 200

        # Now should see exactly one agent
        list_response = await isolated_client.get("/agents")
        assert list_response.status_code == 200
        agents = list_response.json()
        assert len(agents) == 1
        assert agents[0]["name"] == agent_data["name"]

    @pytest.mark.asyncio
    # #
    async def test_agents_list_consistency(self, isolated_client, test_data_factory):
        """
        Test that agent list endpoint returns consistent data with individual gets.
        This validates that LIST, GET by ID, and GET by name all return consistent schemas.
        """
        # Register multiple agents
        agents_data = [
            test_data_factory["create_agent_data"](f"consistency-agent-{i}")
            for i in range(3)
        ]

        created_agents = []
        for agent_data in agents_data:
            response = await isolated_client.post("/agents/register", json=agent_data)
            assert response.status_code == 200
            created_agents.append(response.json())

        # Get all agents via list endpoint
        list_response = await isolated_client.get("/agents")
        assert list_response.status_code == 200
        agents_from_list = list_response.json()
        assert len(agents_from_list) == 3

        # For each agent, verify GET by ID and GET by name return consistent data
        for created_agent in created_agents:
            agent_id = created_agent["id"]
            agent_name = created_agent["name"]

            # Get by ID
            get_by_id_response = await isolated_client.get(f"/agents/{agent_id}")
            assert get_by_id_response.status_code == 200
            agent_by_id = get_by_id_response.json()

            # Get by name
            get_by_name_response = await isolated_client.get(
                f"/agents/name/{agent_name}"
            )
            assert get_by_name_response.status_code == 200
            agent_by_name = get_by_name_response.json()

            # Find the same agent in the list
            agent_from_list = next(
                agent for agent in agents_from_list if agent["id"] == agent_id
            )

            # All three responses should have consistent core fields
            for field in ["id", "name", "description", "acp_type"]:
                assert agent_by_id[field] == created_agent[field]
                assert agent_by_name[field] == created_agent[field]
                assert agent_from_list[field] == created_agent[field]
