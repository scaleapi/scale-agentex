"""
Integration tests for agent task tracker endpoints.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

from datetime import UTC
from unittest import mock

import pytest
import pytest_asyncio
from src.domain.entities.agent_task_tracker import AgentTaskTrackerEntity
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestAgentTaskTrackerAPIIntegration:
    """Integration tests for agent task tracker endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for tracker creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent",
            description="Test agent for tracker testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task(self, isolated_repositories, test_agent):
        """Create a test task for tracker creation"""
        task_repo = isolated_repositories["task_repository"]

        task = TaskEntity(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task for tracker testing",
        )

        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_tracker(self, isolated_repositories, test_agent, test_task):
        """Create a test agent task tracker using the repository"""
        from datetime import datetime

        tracker_repo = isolated_repositories["agent_task_tracker_repository"]

        tracker = AgentTaskTrackerEntity(
            id=orm_id(),
            agent_id=test_agent.id,
            task_id=test_task.id,
            status="PROCESSING",
            status_reason="Test tracker created for integration testing",
            last_processed_event_id=None,
            created_at=datetime.now(UTC),
        )

        return await tracker_repo.create(tracker)

    @pytest_asyncio.fixture
    async def test_event(self, isolated_repositories, test_task, test_agent):
        """Create a test event for event ID references"""
        event_repo = isolated_repositories["event_repository"]

        # Use the correct EventRepository.create method signature
        return await event_repo.create(
            id=orm_id(),
            task_id=test_task.id,
            agent_id=test_agent.id,
            content=None,  # No content needed for our test
        )

    async def test_get_tracker_by_id_returns_correct_data(
        self, isolated_client, test_tracker
    ):
        """Test getting a tracker by ID returns correct data"""
        # When - Get the test tracker by ID
        response = await isolated_client.get(f"/tracker/{test_tracker.id}")

        # Then - Should return the correct tracker with schema validation
        assert response.status_code == 200
        tracker_data = response.json()

        # Validate returned tracker matches our test tracker
        assert tracker_data["id"] == test_tracker.id
        assert tracker_data["agent_id"] == test_tracker.agent_id
        assert tracker_data["task_id"] == test_tracker.task_id
        assert tracker_data["status"] == "PROCESSING"
        assert (
            tracker_data["status_reason"]
            == "Test tracker created for integration testing"
        )

    async def test_list_trackers_returns_valid_structure_and_schema(
        self, isolated_client, test_tracker, test_agent, test_task
    ):
        """Test that list trackers endpoint returns valid array structure with real data"""
        # When - Request all trackers
        response = await isolated_client.get("/tracker")

        # Then - Should succeed with valid list structure and schema
        assert response.status_code == 200
        trackers = response.json()
        assert isinstance(trackers, list)
        assert len(trackers) >= 1  # Should have at least our test tracker

        # Validate tracker schema for the trackers we created
        found_test_tracker = False
        for tracker in trackers:
            assert "id" in tracker and isinstance(tracker["id"], str)
            assert "agent_id" in tracker and isinstance(tracker["agent_id"], str)
            assert "task_id" in tracker and isinstance(tracker["task_id"], str)
            assert "status" in tracker

            # Check if this is our test tracker
            if tracker["id"] == test_tracker.id:
                found_test_tracker = True
                assert tracker["agent_id"] == test_agent.id
                assert tracker["task_id"] == test_task.id
                assert tracker["status"] == "PROCESSING"

        assert found_test_tracker, "Test tracker should be present in the list"

    async def test_filter_trackers_by_agent_id(
        self, isolated_client, test_tracker, test_agent
    ):
        """Test filtering trackers by agent_id parameter"""
        # When - Request trackers filtered by agent_id
        response = await isolated_client.get(f"/tracker?agent_id={test_agent.id}")

        # Then - Should return only trackers for that agent
        assert response.status_code == 200
        trackers = response.json()
        assert isinstance(trackers, list)

        # All returned trackers should belong to the specified agent
        for tracker in trackers:
            assert tracker["agent_id"] == test_agent.id

    async def test_filter_trackers_by_task_id(
        self, isolated_client, test_tracker, test_task
    ):
        """Test filtering trackers by task_id parameter"""
        # When - Request trackers filtered by task_id
        response = await isolated_client.get(f"/tracker?task_id={test_task.id}")

        # Then - Should return only trackers for that task
        assert response.status_code == 200
        trackers = response.json()
        assert isinstance(trackers, list)

        # All returned trackers should belong to the specified task
        for tracker in trackers:
            assert tracker["task_id"] == test_task.id

    async def test_filter_trackers_by_agent_id_and_task_id(
        self, isolated_client, test_tracker, test_task, test_agent
    ):
        """Test filtering trackers by task_id parameter"""
        # When - Request trackers filtered by task_id
        response = await isolated_client.get(
            f"/tracker?task_id={test_task.id}&agent_id={test_agent.id}"
        )

        # Then - Should return only trackers for that task
        assert response.status_code == 200
        trackers = response.json()
        assert isinstance(trackers, list)

        # All returned trackers should belong to the specified task
        for tracker in trackers:
            assert tracker["task_id"] == test_task.id
            assert tracker["agent_id"] == test_agent.id

    async def test_list_trackers_with_order_by(
        self, isolated_client, isolated_repositories
    ):
        """Test that list trackers endpoint supports order_by parameter"""
        # Given - Create an agent and multiple tasks with trackers
        from datetime import datetime

        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="order-by-tracker-agent",
            description="Agent for order_by tracker testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        tracker_repo = isolated_repositories["agent_task_tracker_repository"]

        trackers = []
        for i in range(3):
            task = TaskEntity(
                id=orm_id(),
                name=f"order-tracker-task-{i}",
                status=TaskStatus.RUNNING,
                status_reason=f"Task {i}",
            )
            await task_repo.create(agent_id=agent.id, task=task)

            tracker = AgentTaskTrackerEntity(
                id=orm_id(),
                agent_id=agent.id,
                task_id=task.id,
                status="PROCESSING",
                status_reason=f"Tracker {i}",
                last_processed_event_id=None,
                created_at=datetime.now(UTC),
            )
            trackers.append(await tracker_repo.create(tracker))

        # When - Request trackers with order_by=created_at and order_direction=asc
        response_asc = await isolated_client.get(
            f"/tracker?agent_id={agent.id}&order_by=created_at&order_direction=asc"
        )

        # Then - Should return trackers in ascending order
        assert response_asc.status_code == 200
        trackers_asc = response_asc.json()
        assert len(trackers_asc) == 3

        # Verify ascending order
        for i in range(len(trackers_asc) - 1):
            assert trackers_asc[i]["created_at"] <= trackers_asc[i + 1]["created_at"]

        # When - Request trackers with order_by=created_at and order_direction=desc
        response_desc = await isolated_client.get(
            f"/tracker?agent_id={agent.id}&order_by=created_at&order_direction=desc"
        )

        # Then - Should return trackers in descending order
        assert response_desc.status_code == 200
        trackers_desc = response_desc.json()
        assert len(trackers_desc) == 3

        # Verify descending order
        for i in range(len(trackers_desc) - 1):
            assert trackers_desc[i]["created_at"] >= trackers_desc[i + 1]["created_at"]

    async def test_update_tracker_success_and_retrieve(
        self, isolated_client, test_tracker
    ):
        """Test updating a tracker via PUT and retrieving updated data"""
        # Given - Updated tracker data (avoiding last_processed_event_id for now to avoid validation complexity)
        update_data = {"status": "COMPLETED", "status_reason": "Updated tracker status"}

        # When - Update tracker via PUT
        response = await isolated_client.put(
            f"/tracker/{test_tracker.id}", json=update_data
        )

        # Then - Should succeed and return updated tracker
        assert response.status_code == 200
        updated_tracker = response.json()

        # Validate updated fields
        assert updated_tracker["id"] == test_tracker.id
        assert updated_tracker["status"] == "COMPLETED"
        assert updated_tracker["status_reason"] == "Updated tracker status"

        # When - Retrieve the updated tracker via GET
        get_response = await isolated_client.get(f"/tracker/{test_tracker.id}")

        # Then - Should return the updated data
        assert get_response.status_code == 200
        retrieved_tracker = get_response.json()
        assert retrieved_tracker["status"] == "COMPLETED"
        assert retrieved_tracker["status_reason"] == "Updated tracker status"

    async def test_commit_cursor_tracker_success_and_retrieve(
        self, isolated_client, test_event, test_tracker
    ):
        """Test updating a tracker via PUT and retrieving updated data"""
        # Given - Updated tracker data (avoiding last_processed_event_id for now to avoid validation complexity)
        update_data = {
            "last_processed_event_id": test_event.id,
            "status": "COMPLETED",
            "status_reason": "Updated tracker status",
        }

        # When - Update tracker via PUT
        response = await isolated_client.put(
            f"/tracker/{test_tracker.id}", json=update_data
        )

        # Then - Should succeed and return updated tracker
        assert response.status_code == 200
        updated_tracker = response.json()

        # Validate updated fields
        assert updated_tracker["id"] == test_tracker.id
        assert updated_tracker["last_processed_event_id"] == test_event.id
        assert updated_tracker["status"] == "COMPLETED"
        assert updated_tracker["status_reason"] == "Updated tracker status"

        # When - Retrieve the updated tracker via GET
        get_response = await isolated_client.get(f"/tracker/{test_tracker.id}")

        # Then - Should return the updated data
        assert get_response.status_code == 200
        retrieved_tracker = get_response.json()
        assert retrieved_tracker["status"] == "COMPLETED"
        assert retrieved_tracker["status_reason"] == "Updated tracker status"

    async def test_commit_cursor_tracker_nonexistent_returns_400(
        self, isolated_client, test_tracker
    ):
        """Test updating a non-existent tracker returns proper error"""
        # When - Update a non-existent tracker
        response = await isolated_client.put(
            f"/tracker/{test_tracker.id}",
            json={
                "last_processed_event_id": "non-existent-event-id",
                "status": "COMPLETED",
            },
        )

        # Then - Should return 400
        assert response.status_code == 400

    async def test_get_tracker_non_existent_returns_400(self, isolated_client):
        """Test getting a non-existent tracker returns proper error"""
        # When - Get a non-existent tracker
        response = await isolated_client.get("/tracker/non-existent-tracker-id")

        # Then - Should return 400 (based on the actual API behavior)
        assert response.status_code == 400

    @mock.patch(
        "src.api.schemas.agent_task_tracker.AgentTaskTracker.model_validate",
        side_effect=Exception("Unexpected error"),
    )
    async def test_500_exceptions_are_handled(
        self, mock_patch, isolated_client, test_tracker, test_task, test_agent
    ):
        """Test 500 exceptions are handled, throwing from model_validate as an example"""
        # Testing get tracker
        response = await isolated_client.get(f"/tracker/{test_tracker.id}")
        assert response.status_code == 500
        error_data = response.json()
        assert error_data["message"] == "Internal server error"

        # Testing update tracker
        update_data = {
            "status": "COMPLETED",
            "status_reason": "Updated tracker status",
        }
        response = await isolated_client.put(
            f"/tracker/{test_tracker.id}", json=update_data
        )
        assert response.status_code == 500
        error_data = response.json()
        assert error_data["message"] == "Internal server error"
