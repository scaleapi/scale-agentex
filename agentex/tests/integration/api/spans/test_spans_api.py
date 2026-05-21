"""
Integration tests for span endpoints following FastAPI async testing best practices.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.spans import SpanEntity
from src.domain.entities.tasks import TaskEntity
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestSpansAPIIntegration:
    """Integration tests for span endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for task creation."""
        agent_repo = isolated_repositories["agent_repository"]
        return await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="spans-test-agent",
                description="Agent for span integration tests",
                acp_url="http://test:8000",
                acp_type=ACPType.SYNC,
            )
        )

    @pytest_asyncio.fixture
    async def test_tasks(self, isolated_repositories, test_agent):
        """Create test tasks that can be referenced by spans via FK."""
        task_repo = isolated_repositories["task_repository"]
        tasks = {}
        for name in [
            "task-a",
            "task-b",
            "task-x",
            "task-y",
            "task-create",
            "task-update",
        ]:
            task = await task_repo.create(
                agent_id=test_agent.id,
                task=TaskEntity(id=orm_id(), name=name),
            )
            tasks[name] = task
        return tasks

    @pytest_asyncio.fixture
    async def test_pagination_spans(self, isolated_repositories):
        """Create spans for pagination tests"""
        span_repo = isolated_repositories["span_repository"]
        spans = []
        for i in range(60):
            span = SpanEntity(
                id=orm_id(),
                trace_id=orm_id(),
                name=f"test-span-{i}",
                start_time=datetime.now(UTC),
            )
            spans.append(await span_repo.create(span))
        return spans

    async def test_create_and_retrieve_span_consistency(
        self, isolated_client, test_tasks
    ):
        """Test span creation and validate POST → GET consistency (API-first)"""
        task_id = test_tasks["task-create"].id

        # Given - Span creation data
        span_data = {
            "trace_id": "test-trace-123",
            "task_id": task_id,
            "name": "test-operation",
            "start_time": "2024-01-01T10:00:00Z",
            "end_time": "2024-01-01T10:00:05Z",
            "input": {"key": "value"},
            "output": {"result": "success"},
            "metadata": {"test": True},
        }

        # When - Create span via POST
        create_response = await isolated_client.post("/spans", json=span_data)

        # Then - Should succeed and return created span
        assert create_response.status_code == 200
        created_span = create_response.json()

        # Validate response has required fields
        assert "id" in created_span
        assert created_span["trace_id"] == span_data["trace_id"]
        assert created_span["task_id"] == task_id
        assert created_span["name"] == span_data["name"]
        span_id = created_span["id"]

        # API-first validation: GET the created span
        get_response = await isolated_client.get(f"/spans/{span_id}")
        assert get_response.status_code == 200
        retrieved_span = get_response.json()

        # Validate POST/GET consistency
        assert retrieved_span["id"] == span_id
        assert retrieved_span["trace_id"] == span_data["trace_id"]
        assert retrieved_span["task_id"] == task_id
        assert retrieved_span["name"] == span_data["name"]
        assert retrieved_span["input"] == span_data["input"]
        assert retrieved_span["output"] == span_data["output"]

    async def test_create_span_without_task_id(self, isolated_client):
        """Test span creation without task_id (should default to null)"""
        span_data = {
            "trace_id": "test-trace-no-task",
            "name": "test-no-task",
            "start_time": "2024-01-01T10:00:00Z",
        }

        create_response = await isolated_client.post("/spans", json=span_data)
        assert create_response.status_code == 200
        created_span = create_response.json()
        assert created_span["task_id"] is None

    async def test_update_span_and_validate_changes(self, isolated_client, test_tasks):
        """Test span update and validate PATCH → GET consistency"""
        task_id = test_tasks["task-update"].id

        # Given - Create a span first
        initial_data = {
            "trace_id": "update-trace-456",
            "name": "initial-name",
            "start_time": "2024-01-01T10:00:00Z",
        }
        create_response = await isolated_client.post("/spans", json=initial_data)
        assert create_response.status_code == 200
        span_id = create_response.json()["id"]

        # When - Update the span including task_id
        update_data = {
            "name": "updated-name",
            "task_id": task_id,
            "parent_id": "parent-id",
            "start_time": "2024-01-01T10:10:00Z",
            "end_time": "2024-01-01T10:10:05Z",
            "input": {"key": "value"},
            "output": {"status": "completed"},
            "data": {"test": True},
        }
        patch_response = await isolated_client.patch(
            f"/spans/{span_id}", json=update_data
        )

        # Then - Should succeed
        assert patch_response.status_code == 200

        # API-first validation: GET updated span
        get_response = await isolated_client.get(f"/spans/{span_id}")
        assert get_response.status_code == 200
        updated_span = get_response.json()

        # Validate changes were applied
        assert updated_span["name"] == "updated-name"
        assert updated_span["task_id"] == task_id
        assert updated_span["output"]["status"] == "completed"
        assert updated_span["parent_id"] == "parent-id"
        assert updated_span["start_time"] == "2024-01-01T10:10:00Z"
        assert updated_span["end_time"] == "2024-01-01T10:10:05Z"
        assert updated_span["input"] == {"key": "value"}
        assert updated_span["data"] == {"test": True}
        assert updated_span["trace_id"] == initial_data["trace_id"]  # Unchanged

        # We can also update trace ID and add values into metadata
        patch_response = await isolated_client.patch(
            f"/spans/{span_id}",
            json={
                "trace_id": "updated-trace-789",
                "data": {"version": "2.0.0"},
            },
        )
        assert patch_response.status_code == 200
        updated_span = patch_response.json()
        assert updated_span["name"] == "updated-name"
        assert updated_span["task_id"] == task_id  # Still set from prior update
        assert updated_span["output"]["status"] == "completed"
        assert updated_span["parent_id"] == "parent-id"
        assert updated_span["start_time"] == "2024-01-01T10:10:00Z"
        assert updated_span["end_time"] == "2024-01-01T10:10:05Z"
        assert updated_span["input"] == {"key": "value"}
        assert updated_span["trace_id"] == "updated-trace-789"
        assert updated_span["data"] == {"test": True, "version": "2.0.0"}

    async def test_list_spans_with_trace_id_filtering(self, isolated_client):
        """Test list spans endpoint with trace_id filtering"""
        # Given - Create spans with different trace_ids
        trace_id_1 = "list-trace-001"
        trace_id_2 = "list-trace-002"

        span1_data = {
            "trace_id": trace_id_1,
            "name": "span-1",
            "start_time": "2024-01-01T10:00:00Z",
        }
        span2_data = {
            "trace_id": trace_id_2,
            "name": "span-2",
            "start_time": "2024-01-01T10:00:00Z",
        }

        create1 = await isolated_client.post("/spans", json=span1_data)
        create2 = await isolated_client.post("/spans", json=span2_data)
        assert create1.status_code == 200
        assert create2.status_code == 200

        all_spans = await isolated_client.get("/spans")
        assert all_spans.status_code == 200
        all_spans_data = all_spans.json()
        assert isinstance(all_spans_data, list)
        assert len(all_spans_data) == 2
        assert all_spans_data[0]["trace_id"] == trace_id_1
        assert all_spans_data[1]["trace_id"] == trace_id_2

        # When - List spans filtered by trace_id
        list_response = await isolated_client.get(f"/spans?trace_id={trace_id_1}")

        # Then - Should return only spans with matching trace_id
        assert list_response.status_code == 200
        spans = list_response.json()
        assert isinstance(spans, list)

        # Validate filtering worked
        for span in spans:
            assert span["trace_id"] == trace_id_1

    async def test_list_spans_with_task_id_filtering(self, isolated_client, test_tasks):
        """Test list spans endpoint with task_id filtering"""
        task_id_a = test_tasks["task-a"].id
        task_id_b = test_tasks["task-b"].id

        for i in range(3):
            resp = await isolated_client.post(
                "/spans",
                json={
                    "trace_id": f"trace-task-filter-{i}",
                    "task_id": task_id_a,
                    "name": f"span-task-a-{i}",
                    "start_time": "2024-01-01T10:00:00Z",
                },
            )
            assert resp.status_code == 200

        for i in range(2):
            resp = await isolated_client.post(
                "/spans",
                json={
                    "trace_id": f"trace-task-filter-b-{i}",
                    "task_id": task_id_b,
                    "name": f"span-task-b-{i}",
                    "start_time": "2024-01-01T10:00:00Z",
                },
            )
            assert resp.status_code == 200

        # One span with no task_id
        resp = await isolated_client.post(
            "/spans",
            json={
                "trace_id": "trace-no-task",
                "name": "span-no-task",
                "start_time": "2024-01-01T10:00:00Z",
            },
        )
        assert resp.status_code == 200

        # When - Filter by task_id_a
        response = await isolated_client.get(f"/spans?task_id={task_id_a}")
        assert response.status_code == 200
        spans = response.json()
        assert len(spans) == 3
        for span in spans:
            assert span["task_id"] == task_id_a

        # When - Filter by task_id_b
        response = await isolated_client.get(f"/spans?task_id={task_id_b}")
        assert response.status_code == 200
        spans = response.json()
        assert len(spans) == 2
        for span in spans:
            assert span["task_id"] == task_id_b

        # When - No filter returns all 6
        response = await isolated_client.get("/spans")
        assert response.status_code == 200
        assert len(response.json()) == 6

    async def test_list_spans_with_combined_trace_and_task_filtering(
        self, isolated_client, test_tasks
    ):
        """Test list spans with both trace_id and task_id filters"""
        shared_trace = "combined-trace"
        task_id_x = test_tasks["task-x"].id
        task_id_y = test_tasks["task-y"].id

        await isolated_client.post(
            "/spans",
            json={
                "trace_id": shared_trace,
                "task_id": task_id_x,
                "name": "span-match",
                "start_time": "2024-01-01T10:00:00Z",
            },
        )
        await isolated_client.post(
            "/spans",
            json={
                "trace_id": shared_trace,
                "task_id": task_id_y,
                "name": "span-same-trace-diff-task",
                "start_time": "2024-01-01T10:00:00Z",
            },
        )
        await isolated_client.post(
            "/spans",
            json={
                "trace_id": "other-trace",
                "task_id": task_id_x,
                "name": "span-diff-trace-same-task",
                "start_time": "2024-01-01T10:00:00Z",
            },
        )

        # When - Filter by both trace_id and task_id
        response = await isolated_client.get(
            f"/spans?trace_id={shared_trace}&task_id={task_id_x}"
        )
        assert response.status_code == 200
        spans = response.json()
        assert len(spans) == 1
        assert spans[0]["name"] == "span-match"
        assert spans[0]["trace_id"] == shared_trace
        assert spans[0]["task_id"] == task_id_x

    async def test_get_span_non_existent(self, isolated_client):
        """Test getting a non-existent span returns 404"""
        # When - Get a non-existent span
        response = await isolated_client.get("/spans/non-existent-id")
        # Then - Should return 404
        assert response.status_code == 404

    async def test_list_spans_pagination(self, isolated_client, test_pagination_spans):
        """Test GET /spans/ endpoint with pagination."""
        # Given - A span record exists
        # (created by test_pagination_spans fixture)

        # When - List all spans with pagination
        response = await isolated_client.get("/spans")
        assert response.status_code == 200
        response_data = response.json()
        # Default limit if none specified
        assert len(response_data) == 50

        page_number = 1
        paginated_spans = []
        while True:
            response = await isolated_client.get(
                "/spans", params={"limit": 7, "page_number": page_number}
            )
            assert response.status_code == 200
            spans_data = response.json()
            paginated_spans.extend(spans_data)
            if len(spans_data) < 1:
                break
            page_number += 1
        assert len(paginated_spans) == len(test_pagination_spans)
        assert {(d["id"], d["name"]) for d in paginated_spans} == {
            (d.id, d.name) for d in test_pagination_spans
        }

    async def test_list_spans_with_order_by(self, isolated_client):
        """Test that list spans endpoint supports order_by parameter"""
        # Given - Create multiple spans with different start times
        trace_id = "order-by-trace"
        spans_data = [
            {
                "trace_id": trace_id,
                "name": f"order-span-{i}",
                "start_time": f"2024-01-01T10:0{i}:00Z",
            }
            for i in range(3)
        ]

        for span_data in spans_data:
            response = await isolated_client.post("/spans", json=span_data)
            assert response.status_code == 200

        # When - Request spans with order_by=start_time and order_direction=asc
        response_asc = await isolated_client.get(
            f"/spans?trace_id={trace_id}&order_by=start_time&order_direction=asc"
        )

        # Then - Should return spans in ascending order
        assert response_asc.status_code == 200
        spans_asc = response_asc.json()
        assert len(spans_asc) == 3

        # Verify ascending order
        for i in range(len(spans_asc) - 1):
            assert spans_asc[i]["start_time"] <= spans_asc[i + 1]["start_time"]

        # When - Request spans with order_by=start_time and order_direction=desc
        response_desc = await isolated_client.get(
            f"/spans?trace_id={trace_id}&order_by=start_time&order_direction=desc"
        )

        # Then - Should return spans in descending order
        assert response_desc.status_code == 200
        spans_desc = response_desc.json()
        assert len(spans_desc) == 3

        # Verify descending order
        for i in range(len(spans_desc) - 1):
            assert spans_desc[i]["start_time"] >= spans_desc[i + 1]["start_time"]

        # Verify the order is actually reversed
        assert spans_asc[0]["id"] == spans_desc[-1]["id"]
        assert spans_asc[-1]["id"] == spans_desc[0]["id"]
