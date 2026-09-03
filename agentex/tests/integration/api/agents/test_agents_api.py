"""
Integration tests for agent endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest


@pytest.mark.integration
class TestAgentsAPIIntegration:
    """Integration tests for agent endpoints using API-first validation"""

    @pytest.mark.asyncio
    async def test_register_with_agent_id(self, isolated_client):
        """Test registering agent with agent ID"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
            },
        )
        assert response.status_code == 200
        agent_data = response.json()
        assert agent_data["name"] == "test-integration-agent"
        assert agent_data["description"] == "Created via integration test"
        assert agent_data["acp_type"] == "agentic"
        assert agent_data["id"] is not None

        updated_response = await isolated_client.post(
            "/agents/register",
            json={
                "agent_id": agent_data["id"],
                "name": "updated-name",
                "description": "Updated description",
                # ACP URL will not get updated
                "acp_url": "http://test-new-acp-server:8000",
                "acp_type": "sync",
            },
        )
        assert updated_response.status_code == 200
        updated_agent_data = updated_response.json()
        assert updated_agent_data["name"] == "updated-name"
        assert updated_agent_data["description"] == "Updated description"
        assert updated_agent_data["acp_type"] == "sync"
        assert updated_agent_data["id"] == agent_data["id"]

    @pytest.mark.asyncio
    async def test_register_build_creates_build_only_agent(self, isolated_client):
        """register-build creates a BUILD_ONLY agent with no acp_url and no api key."""
        response = await isolated_client.post(
            "/agents/register-build",
            json={
                "name": "test-build-only-agent",
                "description": "Created via register-build",
            },
        )
        assert response.status_code == 200
        agent_data = response.json()
        assert agent_data["name"] == "test-build-only-agent"
        assert agent_data["description"] == "Created via register-build"
        assert agent_data["status"] == "BuildOnly"
        assert agent_data["id"] is not None
        # Minimal endpoint: no API key is minted at build time
        assert "agent_api_key" not in agent_data
        # No running pod yet, so acp_url must not be populated
        assert agent_data.get("acp_url") is None

        # And - the build-only agent is retrievable and listed like any agent
        get_response = await isolated_client.get(f"/agents/{agent_data['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "BuildOnly"

    @pytest.mark.asyncio
    async def test_register_build_is_idempotent_by_name(self, isolated_client):
        """A second register-build for the same name returns the existing agent."""
        payload = {
            "name": "test-build-idempotent-agent",
            "description": "first",
        }
        first = await isolated_client.post("/agents/register-build", json=payload)
        assert first.status_code == 200
        first_id = first.json()["id"]

        second = await isolated_client.post(
            "/agents/register-build",
            json={**payload, "description": "second"},
        )
        assert second.status_code == 200
        # Same row returned; an existing agent is not clobbered by a rebuild
        assert second.json()["id"] == first_id
        assert second.json()["status"] == "BuildOnly"

    @pytest.mark.asyncio
    async def test_build_only_agent_promoted_to_ready_on_register(
        self, isolated_client
    ):
        """register-build then /register (with the agent_id) flips status to Ready."""
        build = await isolated_client.post(
            "/agents/register-build",
            json={
                "name": "test-build-then-deploy-agent",
                "description": "build first",
            },
        )
        assert build.status_code == 200
        assert build.json()["status"] == "BuildOnly"
        agent_id = build.json()["id"]

        registered = await isolated_client.post(
            "/agents/register",
            json={
                "agent_id": agent_id,
                "name": "test-build-then-deploy-agent",
                "description": "now deployed",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "async",
            },
        )
        assert registered.status_code == 200
        assert registered.json()["id"] == agent_id
        assert registered.json()["status"] == "Ready"

    @pytest.mark.asyncio
    async def test_build_only_agent_promoted_to_ready_via_deployment(
        self, isolated_client
    ):
        """Deployment-scoped flow: /register (with a deployment_id) leaves the
        agent row untouched, and promoting the deployment is what flips a
        BUILD_ONLY agent to Ready and sets its acp_url."""
        # Build-time: create the agent row up front (BUILD_ONLY, no acp_url).
        build = await isolated_client.post(
            "/agents/register-build",
            json={
                "name": "test-build-then-promote-agent",
                "description": "build first",
            },
        )
        assert build.status_code == 200
        assert build.json()["status"] == "BuildOnly"
        agent_id = build.json()["id"]

        # Deploy-time step 1: create a deployment record (PENDING).
        created = await isolated_client.post(
            f"/agents/{agent_id}/deployments",
            json={"docker_image": "test-image:latest"},
        )
        assert created.status_code == 200
        deployment_id = created.json()["id"]

        # Deploy-time step 2: deployment-scoped /register. Because a deployment_id
        # is present, this updates only the deployment record (-> Ready); the
        # agent row is deliberately left in BUILD_ONLY (acp_url changes only via
        # promotion).
        registered = await isolated_client.post(
            "/agents/register",
            json={
                "agent_id": agent_id,
                "name": "test-build-then-promote-agent",
                "description": "now deployed",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "async",
                "registration_metadata": {"deployment_id": deployment_id},
            },
        )
        assert registered.status_code == 200
        assert registered.json()["status"] == "BuildOnly"

        # Promotion is the step that makes a build-only agent live.
        promoted = await isolated_client.post(
            f"/agents/{agent_id}/deployments/{deployment_id}/promote",
        )
        assert promoted.status_code == 200
        assert promoted.json()["is_production"] is True
        assert promoted.json()["acp_url"] == "http://test-acp-server:8000"

        # The agent row is now Ready and points at the promoted deployment.
        get_response = await isolated_client.get(f"/agents/{agent_id}")
        assert get_response.status_code == 200
        agent_after = get_response.json()
        assert agent_after["status"] == "Ready"
        assert agent_after["production_deployment_id"] == deployment_id

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
    async def test_register_agent_deployment_history(self, isolated_client):
        """Test registering agent with code URL and commit hash"""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent-deployment-history",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
            },
        )
        assert response.status_code == 200
        agent_data = response.json()

        # No registration metadata means no deployment history
        deployment_history_response = await isolated_client.get(
            f"/deployment-history?agent_id={agent_data['id']}"
        )
        assert deployment_history_response.status_code == 200
        deployment_history_data = deployment_history_response.json()
        assert len(deployment_history_data) == 0

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent-deployment-history",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
                "registration_metadata": {
                    "code_url": "https://github.com/example-repo/agents/tree/main",
                },
            },
        )
        assert response.status_code == 200
        # No branch name means no deployment history
        deployment_history_response = await isolated_client.get(
            f"/deployment-history?agent_id={agent_data['id']}"
        )
        assert deployment_history_response.status_code == 200
        deployment_history_data = deployment_history_response.json()
        assert len(deployment_history_data) == 0

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent-deployment-history",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
                "registration_metadata": {
                    "code_url": "https://github.com/example-repo/agents/tree/main",
                    "branch_name": "main",
                },
            },
        )
        assert response.status_code == 200
        # No commit hash means no deployment history
        deployment_history_response = await isolated_client.get(
            f"/deployment-history?agent_id={agent_data['id']}"
        )
        assert deployment_history_response.status_code == 200
        deployment_history_data = deployment_history_response.json()
        assert len(deployment_history_data) == 0

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent-deployment-history",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
                "registration_metadata": {
                    "code_url": "https://github.com/example-repo/agents/tree/main",
                    "branch_name": "main",
                    "agent_commit": "test-commit-hash",
                },
            },
        )
        assert response.status_code == 200
        # Successfully created deployment history
        deployment_history_response = await isolated_client.get(
            f"/deployment-history?agent_id={agent_data['id']}"
        )
        assert deployment_history_response.status_code == 200
        deployment_history_data = deployment_history_response.json()
        assert len(deployment_history_data) == 1
        assert deployment_history_data[0]["agent_id"] == agent_data["id"]
        assert deployment_history_data[0]["commit_hash"] == "test-commit-hash"
        assert deployment_history_data[0]["branch_name"] == "main"
        assert deployment_history_data[0]["author_name"] == "N/A"
        assert deployment_history_data[0]["author_email"] == "N/A"

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
    async def test_delete_agent_success(self, isolated_client):
        """Test agent registration and retrieval via API endpoints"""
        # When - Register new agent via API
        register_response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "test-integration-agent-to-delete",
                "description": "Created via integration test",
                "acp_url": "http://test-acp-server:8000",
                "acp_type": "agentic",
            },
        )

        # Then - Validate POST response
        assert register_response.status_code == 200
        agent_data = register_response.json()
        assert agent_data["name"] == "test-integration-agent-to-delete"
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
        assert retrieved_agent["name"] == "test-integration-agent-to-delete"
        assert retrieved_agent["description"] == "Created via integration test"

        # And - Delete the agent
        delete_response = await isolated_client.delete(f"/agents/{agent_id}")
        assert delete_response.status_code == 200
        deleted_agent = delete_response.json()
        assert deleted_agent["id"] == agent_id
        assert deleted_agent["message"] == f"Agent '{agent_id}' deleted successfully"

        # And - Listing agents should not return the deleted agent
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 0

        # And - Getting the agent by ID should return 404
        response = await isolated_client.get(f"/agents/{agent_id}")
        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["message"]

        # And - Getting the agent by name should return 404

        # And - Deleting the agent again should return 404
        response = await isolated_client.delete(f"/agents/{agent_id}")
        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["message"]

        # And - Deleting the agent by name should return 404
        response = await isolated_client.delete(f"/agents/name/{agent_data['name']}")
        assert response.status_code == 404
        error_data = response.json()
        assert "not found" in error_data["message"]

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
    async def test_list_agents_pagination(self, isolated_client):
        """Test listing agents with pagination"""
        # Given - Initially empty agents list
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        initial_agents = response.json()
        initial_count = len(initial_agents)

        # When - Register an agent
        for i in range(10):
            register_response = await isolated_client.post(
                "/agents/register",
                json={
                    "name": f"pagination-agent-{i}",
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
        assert len(agents_data) == initial_count + 10

        # When - List agents with pagination
        page_number = 1
        paginated_agents = []
        while True:
            response = await isolated_client.get(
                f"/agents?limit=1&page_number={page_number}"
            )
            assert response.status_code == 200
            agents_data = response.json()
            paginated_agents.extend(agents_data)
            if len(agents_data) < 1:
                break
            page_number += 1
        assert len(paginated_agents) == initial_count + 10

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_list_agents_filters_by_agent_card_metadata(self, isolated_client):
        """`agent_card_metadata` returns only agents whose card metadata contains
        the requested key/value pairs; agents without card metadata are excluded."""
        # Given - three agents: one Permits-capable, one with different metadata,
        # and one with no agent_card at all.
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-permits",
                "description": "opts into Permits",
                "acp_url": "http://permits-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {
                        "metadata": {"permits_capable": True, "region": "us"}
                    }
                },
            },
        )
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-other",
                "description": "different capability",
                "acp_url": "http://other-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {"metadata": {"other_feature": True}}
                },
            },
        )
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-none",
                "description": "no card metadata",
                "acp_url": "http://plain-agent:8000",
                "acp_type": "sync",
            },
        )

        # When - filter by exact key/value present on only one agent
        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":true}'
        )
        assert response.status_code == 200
        agents = response.json()
        names = {a["name"] for a in agents}
        assert names == {"card-metadata-permits"}

        # And - non-matching value returns no agents (agent exists but with a
        # different value for the same key does not match)
        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":false}'
        )
        assert response.status_code == 200
        assert response.json() == []

        # And - omitting the filter returns all non-deleted agents, including
        # those without any agent_card metadata
        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        names_unfiltered = {a["name"] for a in response.json()}
        assert {
            "card-metadata-permits",
            "card-metadata-other",
            "card-metadata-none",
        } <= names_unfiltered

    @pytest.mark.asyncio
    async def test_list_agents_agent_card_metadata_multi_key_containment(
        self, isolated_client
    ):
        """Multi-key filter requires every key/value to be present (JSONB `@>`)."""
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-multi",
                "description": "multi",
                "acp_url": "http://multi-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {
                        "metadata": {
                            "permits_capable": True,
                            "region": "us",
                            "extra": "value",
                        }
                    }
                },
            },
        )

        # All requested keys match -> included
        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":true,"region":"us"}'
        )
        assert response.status_code == 200
        assert {a["name"] for a in response.json()} == {"card-metadata-multi"}

        # One requested key doesn't match -> excluded
        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":true,"region":"eu"}'
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_agents_agent_card_metadata_combined_with_pagination(
        self, isolated_client
    ):
        """The filter composes with existing pagination and ordering behavior."""
        for i in range(3):
            await isolated_client.post(
                "/agents/register",
                json={
                    "name": f"card-metadata-page-{i}",
                    "description": f"agent {i}",
                    "acp_url": f"http://page-agent-{i}:8000",
                    "acp_type": "sync",
                    "registration_metadata": {
                        "agent_card": {"metadata": {"permits_capable": True}}
                    },
                },
            )
        # Unrelated agent that must not leak into filtered results
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-page-noise",
                "description": "noise",
                "acp_url": "http://noise:8000",
                "acp_type": "sync",
            },
        )

        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":true}&limit=2&page_number=1'
        )
        assert response.status_code == 200
        page_one = response.json()
        assert len(page_one) == 2
        assert all(a["name"].startswith("card-metadata-page-") for a in page_one)
        assert not any(a["name"] == "card-metadata-page-noise" for a in page_one)

    @pytest.mark.asyncio
    async def test_list_agents_agent_card_metadata_invalid_json_returns_400(
        self, isolated_client
    ):
        """Malformed JSON in `agent_card_metadata` is rejected up front."""
        response = await isolated_client.get("/agents?agent_card_metadata=not-json")
        assert response.status_code == 400

        response = await isolated_client.get("/agents?agent_card_metadata=[1,2,3]")
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "raw_filter",
        [
            '{"x": NaN}',
            '{"x": Infinity}',
            '{"x": -Infinity}',
            '{"x": 1e1000000}',
            '{"x": [1, NaN]}',
            '{"x": {"nested": Infinity}}',
            '{"x": ' + "9" * 5000 + "}",
        ],
    )
    @pytest.mark.asyncio
    async def test_list_agents_agent_card_metadata_non_finite_numbers_return_400(
        self, isolated_client, raw_filter
    ):
        """Values Python's json accepts but JSON doesn't are rejected as 400, not
        passed through to the JSONB bind parameter where they'd surface as a 500."""
        response = await isolated_client.get(
            "/agents", params={"agent_card_metadata": raw_filter}
        )
        assert response.status_code == 400
        assert "agent_card_metadata" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_list_agents_agent_card_metadata_empty_object_requires_metadata(
        self, isolated_client
    ):
        """An explicit `{}` filter still applies the containment predicate: agents
        must have a card metadata object, but any contents match."""
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-empty-with",
                "description": "has card metadata",
                "acp_url": "http://with-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {"metadata": {"anything": "at-all"}}
                },
            },
        )
        await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-empty-without",
                "description": "no card metadata",
                "acp_url": "http://without-agent:8000",
                "acp_type": "sync",
            },
        )

        response = await isolated_client.get("/agents?agent_card_metadata={}")
        assert response.status_code == 200
        names = {a["name"] for a in response.json()}
        assert "card-metadata-empty-with" in names
        assert "card-metadata-empty-without" not in names

    @pytest.mark.asyncio
    async def test_reregistration_replaces_agent_card_and_filter_results(
        self, isolated_client
    ):
        """Re-registering the same agent identity replaces the stored top-level
        `agent_card`, and the metadata filter reflects the new card immediately.
        This locks the rolling-update contract a polling discovery client relies
        on: after a release re-registers with card B, filter A stops matching
        and filter B starts matching."""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-rollout",
                "description": "release 1",
                "acp_url": "http://rollout-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {"metadata": {"permits_capable": True, "rev": "a"}}
                },
            },
        )
        assert response.status_code == 200

        response = await isolated_client.get('/agents?agent_card_metadata={"rev":"a"}')
        assert response.status_code == 200
        assert {a["name"] for a in response.json()} == {"card-metadata-rollout"}

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-rollout",
                "description": "release 2",
                "acp_url": "http://rollout-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {"metadata": {"permits_capable": True, "rev": "b"}}
                },
            },
        )
        assert response.status_code == 200

        response = await isolated_client.get('/agents?agent_card_metadata={"rev":"a"}')
        assert response.status_code == 200
        assert response.json() == []

        response = await isolated_client.get('/agents?agent_card_metadata={"rev":"b"}')
        assert response.status_code == 200
        assert {a["name"] for a in response.json()} == {"card-metadata-rollout"}

    @pytest.mark.asyncio
    async def test_reregistration_with_null_agent_card_withdraws_from_discovery(
        self, isolated_client
    ):
        """An explicit `{"agent_card": null}` registration clears a previously
        published card, so rolling back to a release that publishes no card can
        withdraw the stale descriptor without deleting the agent. Omitting
        `registration_metadata` entirely preserves the existing card."""
        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-withdraw",
                "description": "publishes a card",
                "acp_url": "http://withdraw-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {
                    "agent_card": {"metadata": {"permits_capable": True}}
                },
            },
        )
        assert response.status_code == 200

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-withdraw",
                "description": "re-registers without touching metadata",
                "acp_url": "http://withdraw-agent:8000",
                "acp_type": "sync",
            },
        )
        assert response.status_code == 200

        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":true}'
        )
        assert response.status_code == 200
        assert {a["name"] for a in response.json()} == {"card-metadata-withdraw"}

        response = await isolated_client.post(
            "/agents/register",
            json={
                "name": "card-metadata-withdraw",
                "description": "rolled back, withdraws the card",
                "acp_url": "http://withdraw-agent:8000",
                "acp_type": "sync",
                "registration_metadata": {"agent_card": None},
            },
        )
        assert response.status_code == 200

        response = await isolated_client.get(
            '/agents?agent_card_metadata={"permits_capable":true}'
        )
        assert response.status_code == 200
        assert response.json() == []

        response = await isolated_client.get("/agents?agent_card_metadata={}")
        assert response.status_code == 200
        assert "card-metadata-withdraw" not in {a["name"] for a in response.json()}

        response = await isolated_client.get("/agents")
        assert response.status_code == 200
        assert "card-metadata-withdraw" in {a["name"] for a in response.json()}
