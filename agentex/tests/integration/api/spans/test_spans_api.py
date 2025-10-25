"""
Integration tests for span endpoints following FastAPI async testing best practices.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest


@pytest.mark.asyncio
class TestSpansAPIIntegration:
    """Integration tests for span endpoints using API-first validation"""

    async def test_create_and_retrieve_span_consistency(self, isolated_client):
        """Test span creation and validate POST → GET consistency (API-first)"""
        # Given - Span creation data
        span_data = {
            "trace_id": "test-trace-123",
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
        assert created_span["name"] == span_data["name"]
        span_id = created_span["id"]

        # API-first validation: GET the created span
        get_response = await isolated_client.get(f"/spans/{span_id}")
        assert get_response.status_code == 200
        retrieved_span = get_response.json()

        # Validate POST/GET consistency
        assert retrieved_span["id"] == span_id
        assert retrieved_span["trace_id"] == span_data["trace_id"]
        assert retrieved_span["name"] == span_data["name"]
        assert retrieved_span["input"] == span_data["input"]
        assert retrieved_span["output"] == span_data["output"]

    async def test_update_span_and_validate_changes(self, isolated_client):
        """Test span update and validate PATCH → GET consistency"""
        # Given - Create a span first
        initial_data = {
            "trace_id": "update-trace-456",
            "name": "initial-name",
            "start_time": "2024-01-01T10:00:00Z",
        }
        create_response = await isolated_client.post("/spans", json=initial_data)
        assert create_response.status_code == 200
        span_id = create_response.json()["id"]

        # When - Update the span
        update_data = {
            "name": "updated-name",
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
        assert updated_span["output"]["status"] == "completed"
        assert updated_span["parent_id"] == "parent-id"
        assert updated_span["start_time"] == "2024-01-01T10:10:00Z"
        assert updated_span["end_time"] == "2024-01-01T10:10:05Z"
        assert updated_span["input"] == {"key": "value"}
        assert updated_span["trace_id"] == "updated-trace-789"
        assert updated_span["data"] == {"test": True, "version": "2.0.0"}

    async def test_list_spans_with_filtering(self, isolated_client):
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

    async def test_get_span_non_existent(self, isolated_client):
        """Test getting a non-existent span returns 404"""
        # When - Get a non-existent span
        response = await isolated_client.get("/spans/non-existent-id")
        print("--------------------------------ASDF ASDF")
        print(response.status_code, response.json())

        # Then - Should return 404
        assert response.status_code == 404
