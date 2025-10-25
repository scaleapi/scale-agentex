"""
Integration tests for deployment history endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.deployment_history import DeploymentHistoryEntity
from src.utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeploymentHistoryIntegration:
    """Integration tests for deployment history endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for deployment history testing"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent",
            description="Test agent for deployment history testing",
            acp_type=ACPType.SYNC,
            acp_url="http://test-acp:8000",
            registration_metadata=None,
            registered_at=None,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_deployment(self, isolated_repositories, test_agent):
        """Create a test deployment record for the test agent"""
        deployment_repo = isolated_repositories.get("deployment_history_repository")
        if not deployment_repo:
            # If deployment repository is not in isolated_repositories, skip database-dependent tests
            pytest.skip("Deployment history repository not available in test setup")

        deployment = DeploymentHistoryEntity(
            id=orm_id(),
            agent_id=test_agent.id,
            author_name="Test Author",
            author_email="test@example.com",
            branch_name="test-branch",
            build_timestamp=datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC),
            deployment_timestamp=datetime(2025, 10, 1, 12, 5, 0, tzinfo=UTC),
            commit_hash="test-commit-hash-123",
        )
        return await deployment_repo.create(deployment)

    async def test_get_deployment(self, isolated_client, test_deployment):
        """Test GET /deployment-history/{deployment_id} endpoint."""
        # Given - A deployment record exists
        # (created by test_deployment fixture)

        # When - Get the deployment by ID
        response = await isolated_client.get(
            f"/deployment-history/{test_deployment.id}"
        )

        # Then - Should return the deployment
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == test_deployment.id
        assert response_data["agent_id"] == test_deployment.agent_id

    async def test_get_deployment_non_existent(self, isolated_client):
        """Test GET /deployment-history/{deployment_id} endpoint with non-existent deployment ID."""
        # Given - A non-existent deployment ID
        non_existent_id = "non-existent-id"

        # When - Get the deployment by ID
        response = await isolated_client.get(f"/deployment-history/{non_existent_id}")

        # Then - Should return 404
        assert response.status_code == 404
        response_data = response.json()
        assert "Deployment not found" in response_data["message"]

    async def test_list_deployments_by_agent_id(self, isolated_client, test_deployment):
        """Test GET /deployment-history/ endpoint with agent ID."""
        # Given - A deployment record exists
        # (created by test_deployment fixture)

        # When - List all deployments by agent ID
        response = await isolated_client.get(
            "/deployment-history", params={"agent_id": test_deployment.agent_id}
        )

        # Then - Should return the deployment
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["id"] == test_deployment.id

    async def test_list_deployments_by_agent_name(
        self, isolated_client, test_deployment, test_agent
    ):
        """Test GET /deployment-history/ endpoint with agent name."""
        # Given - A deployment record exists
        # (created by test_deployment fixture)

        # When - List all deployments by agent name
        response = await isolated_client.get(
            "/deployment-history", params={"agent_name": test_agent.name}
        )

        # Then - Should return the deployment
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1

    async def test_invalid_list_deployments(
        self, isolated_client, test_deployment, test_agent
    ):
        """Test GET /deployment-history/ endpoint with invalid parameters."""

        response = await isolated_client.get("/deployment-history")
        assert response.status_code == 400
        response_data = response.json()
        assert "message" in response_data
        assert (
            "Either 'agent_id' or 'agent_name' must be provided to list deployment history."
            in response_data["message"]
        )

        response = await isolated_client.get(
            "/deployment-history",
            params={
                "agent_id": test_deployment.agent_id,
                "agent_name": test_agent.name,
            },
        )
        assert response.status_code == 400
        response_data = response.json()
        assert "message" in response_data
        assert (
            "Only one of 'agent_id' or 'agent_name' should be provided to list deployment history."
            in response_data["message"]
        )

        response = await isolated_client.get(
            "/deployment-history", params={"agent_name": "non-existent-agent"}
        )
        assert response.status_code == 404
        response_data = response.json()
        assert "message" in response_data
        assert "does not exist" in response_data["message"]
