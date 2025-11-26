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

    @pytest_asyncio.fixture
    async def test_pagination_deployments(self, isolated_repositories, test_agent):
        """Create a test deployment record for the test agent"""
        deployment_repo = isolated_repositories.get("deployment_history_repository")
        if not deployment_repo:
            # If deployment repository is not in isolated_repositories, skip database-dependent tests
            pytest.skip("Deployment history repository not available in test setup")

        deployments = []
        for i in range(60):
            deployment = DeploymentHistoryEntity(
                id=orm_id(),
                agent_id=test_agent.id,
                author_name="Test Author",
                author_email="test@example.com",
                branch_name="test-branch",
                build_timestamp=datetime(2025, 10, 1, 12, 0, 0, tzinfo=UTC),
                deployment_timestamp=datetime(2025, 10, 1, 12, 5, 0, tzinfo=UTC),
                commit_hash=f"test-commit-hash-{i}",
            )
            deployments.append(await deployment_repo.create(deployment))
        return deployments

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

    async def test_list_deployments_pagination(
        self, isolated_client, test_pagination_deployments, test_agent
    ):
        """Test GET /deployment-history/ endpoint with pagination."""
        # Given - A deployment record exists
        # (created by test_pagination_deployments fixture)

        # When - List all deployments with pagination
        response = await isolated_client.get(
            "/deployment-history", params={"agent_id": test_agent.id}
        )
        assert response.status_code == 200
        response_data = response.json()
        # Default limit if none specified
        assert len(response_data) == 50

        page_number = 1
        paginated_deployments = []
        while True:
            response = await isolated_client.get(
                "/deployment-history",
                params={
                    "limit": 7,
                    "page_number": page_number,
                    "agent_id": test_agent.id,
                },
            )
            assert response.status_code == 200
            deployments_data = response.json()
            paginated_deployments.extend(deployments_data)
            if len(deployments_data) < 1:
                break
            page_number += 1
        assert len(paginated_deployments) == len(test_pagination_deployments)
        assert {(d["id"], d["commit_hash"]) for d in paginated_deployments} == {
            (d.id, d.commit_hash) for d in test_pagination_deployments
        }

    async def test_list_deployments_with_order_by(
        self, isolated_client, isolated_repositories
    ):
        """Test GET /deployment-history/ endpoint with order_by parameter."""
        # Given - Create an agent and multiple deployments
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="order-by-deployment-agent",
            description="Agent for order_by deployment testing",
            acp_type=ACPType.SYNC,
            acp_url="http://test-acp:8000",
            registration_metadata=None,
            registered_at=None,
        )
        await agent_repo.create(agent)

        deployment_repo = isolated_repositories.get("deployment_history_repository")
        if not deployment_repo:
            pytest.skip("Deployment history repository not available in test setup")

        deployments = []
        for i in range(3):
            deployment = DeploymentHistoryEntity(
                id=orm_id(),
                agent_id=agent.id,
                author_name="Test Author",
                author_email="test@example.com",
                branch_name="test-branch",
                build_timestamp=datetime(2025, 10, 1, 12, i, 0, tzinfo=UTC),
                deployment_timestamp=datetime(2025, 10, 1, 12, 5, i, tzinfo=UTC),
                commit_hash=f"order-test-commit-{i}",
            )
            deployments.append(await deployment_repo.create(deployment))

        # When - Request deployments with order_by=deployment_timestamp and order_direction=asc
        response_asc = await isolated_client.get(
            "/deployment-history",
            params={
                "agent_id": agent.id,
                "order_by": "deployment_timestamp",
                "order_direction": "asc",
            },
        )

        # Then - Should return deployments in ascending order
        assert response_asc.status_code == 200
        deployments_asc = response_asc.json()
        assert len(deployments_asc) == 3

        # Verify ascending order
        for i in range(len(deployments_asc) - 1):
            assert (
                deployments_asc[i]["deployment_timestamp"]
                <= deployments_asc[i + 1]["deployment_timestamp"]
            )

        # When - Request deployments with order_by=deployment_timestamp and order_direction=desc
        response_desc = await isolated_client.get(
            "/deployment-history",
            params={
                "agent_id": agent.id,
                "order_by": "deployment_timestamp",
                "order_direction": "desc",
            },
        )

        # Then - Should return deployments in descending order
        assert response_desc.status_code == 200
        deployments_desc = response_desc.json()
        assert len(deployments_desc) == 3

        # Verify descending order
        for i in range(len(deployments_desc) - 1):
            assert (
                deployments_desc[i]["deployment_timestamp"]
                >= deployments_desc[i + 1]["deployment_timestamp"]
            )

        # Verify the order is actually reversed
        assert deployments_asc[0]["id"] == deployments_desc[-1]["id"]
        assert deployments_asc[-1]["id"] == deployments_desc[0]["id"]

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
