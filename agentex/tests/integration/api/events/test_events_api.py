"""
Integration tests for event endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.task_messages import TextContentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.integration
class TestEventsAPIIntegration:
    """Integration tests for event endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for event creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent",
            description="Test agent for event testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task(self, isolated_repositories, test_agent):
        """Create a test task for event creation"""
        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task for event testing",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_event(self, isolated_repositories, test_agent, test_task):
        """Create a test event using the repository"""
        event_repo = isolated_repositories["event_repository"]

        content = TextContentEntity(
            type="text", author="user", content="Test event content"
        )

        return await event_repo.create(
            id=orm_id(), task_id=test_task.id, agent_id=test_agent.id, content=content
        )

    @pytest.mark.asyncio
    async def test_get_event_by_id_and_schema_validation(
        self, isolated_client, test_event
    ):
        """Test get event by ID and validate event schema structure"""
        # Test 404 for non-existent event
        non_existent_id = "non-existent-event-id"
        response = await isolated_client.get(f"/events/{non_existent_id}")
        assert response.status_code == 404

        # Test 200 for existing event
        response = await isolated_client.get(f"/events/{test_event.id}")
        assert response.status_code == 200
        assert response.json()["id"] == test_event.id

        # Note: Since events are created through other processes, we test schema
        # validation when we encounter events through the list endpoint

    @pytest.mark.asyncio
    async def test_list_events_with_required_filters_and_schema(
        self, isolated_client, test_agent, test_task, test_event
    ):
        """Test list events endpoint with required filters and validate schema"""
        # Events endpoint requires both task_id and agent_id as required parameters

        # Test missing required parameters return 422
        response = await isolated_client.get("/events")
        assert response.status_code == 422  # Missing required query params

        response = await isolated_client.get("/events?task_id=test-task")
        assert response.status_code == 422  # Missing agent_id

        response = await isolated_client.get("/events?agent_id=test-agent")
        assert response.status_code == 422  # Missing task_id

        # Valid request with both required parameters
        response = await isolated_client.get(
            f"/events?task_id={test_task.id}&agent_id={test_agent.id}"
        )
        assert response.status_code == 200
        events = response.json()
        assert isinstance(events, list)
        assert len(events) == 1

        # Validate event schema for any existing events
        for event in events:
            # Required fields
            assert (
                "id" in event and isinstance(event["id"], str) and len(event["id"]) > 0
            )
            assert "sequence_id" in event and isinstance(event["sequence_id"], int)
            assert "task_id" in event and event["task_id"] == test_task.id
            assert "agent_id" in event and event["agent_id"] == test_agent.id

            # Optional timestamp field
            if "created_at" in event and event["created_at"] is not None:
                assert (
                    isinstance(event["created_at"], str) and "T" in event["created_at"]
                )

    @pytest.mark.asyncio
    async def test_list_events_with_optional_filters(self, isolated_client):
        """Test list events endpoint with optional filtering parameters"""
        test_task_id = "test-task-id"
        test_agent_id = "test-agent-id"

        # Test with optional last_processed_event_id filter
        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&last_processed_event_id=some-event-id"
        )
        assert response.status_code == 200

        # Test with optional limit filter
        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&limit=10"
        )
        assert response.status_code == 200

        # Test with both optional filters
        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&last_processed_event_id=some-event&limit=5"
        )
        assert response.status_code == 200

        # Test limit validation (should accept valid range)
        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&limit=1"
        )
        assert response.status_code == 200

        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&limit=1000"
        )
        assert response.status_code == 200

        # Test invalid limit (outside valid range)
        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&limit=0"
        )
        assert response.status_code == 422

        response = await isolated_client.get(
            f"/events?task_id={test_task_id}&agent_id={test_agent_id}&limit=1001"
        )
        assert response.status_code == 422
