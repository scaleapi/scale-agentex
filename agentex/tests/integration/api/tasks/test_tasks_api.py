"""
Integration tests for task endpoints (read-only operations).
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestTasksAPIIntegration:
    """Integration tests for task endpoints using API-first validation"""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        """Create a test agent for task creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent",
            description="Test agent for integration testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task(self, isolated_repositories, test_agent):
        """Create a test task directly via repository (bypass service MongoDB dependency)"""
        task_repo = isolated_repositories["task_repository"]

        # Create a task directly in the PostgreSQL repository
        task = TaskEntity(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )

        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_task_with_params(self, isolated_repositories, test_agent):
        """Create a test task with params directly via repository"""
        task_repo = isolated_repositories["task_repository"]

        task_params = {
            "model": "gpt-4",
            "temperature": 0.8,
            "max_tokens": 2000,
            "nested": {"setting": "value", "numbers": [1, 2, 3]},
        }

        # Create a task with params directly in the PostgreSQL repository
        task = TaskEntity(
            id=orm_id(),
            name="test-task-with-params",
            status=TaskStatus.RUNNING,
            status_reason="Test task with params created for integration testing",
            params=task_params,
        )

        return await task_repo.create(agent_id=test_agent.id, task=task)

    async def test_delete_task_success(
        self, isolated_client, test_task, test_task_with_params
    ):
        """Test that delete task endpoint returns success"""
        # When - Delete the test task
        response = await isolated_client.delete(f"/tasks/{test_task.id}")
        assert response.status_code == 200
        deleted_task = response.json()
        assert deleted_task["id"] == test_task.id
        assert deleted_task["message"] == f"Task {test_task.id} deleted successfully"

        # Then - Should not return the deleted task
        response = await isolated_client.get(f"/tasks/{test_task.id}")
        assert response.status_code == 404
        error_data = response.json()
        assert error_data["message"] == f"Task {test_task.id} not found"

        # And - Delete the test task with params by name
        response = await isolated_client.delete(
            f"/tasks/name/{test_task_with_params.name}"
        )
        assert response.status_code == 200
        deleted_task = response.json()
        assert deleted_task["id"] == test_task_with_params.id
        assert (
            deleted_task["message"]
            == f"Task '{test_task_with_params.name}' deleted successfully"
        )

        # Then - Should not return the deleted task
        response = await isolated_client.get(
            f"/tasks/name/{test_task_with_params.name}"
        )
        assert response.status_code == 404
        error_data = response.json()
        assert error_data["message"] == f"Task {test_task_with_params.name} not found"

        # And - Listing tasks should not return the deleted task
        response = await isolated_client.get("/tasks")
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 0

    async def test_list_tasks_returns_valid_structure_and_schema(
        self, isolated_client, test_task
    ):
        """Test that list tasks endpoint returns valid array structure and schema with real data"""
        # When - Request all tasks
        response = await isolated_client.get("/tasks")

        # Then - Should succeed with valid list structure and schema
        assert response.status_code == 200
        tasks = response.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1  # Should have at least our test task

        # Validate task schema for the tasks we created
        found_test_task = False
        for task in tasks:
            assert "id" in task and isinstance(task["id"], str)

            # Check if this is our test task
            if task["id"] == test_task.id:
                found_test_task = True
                assert task["name"] == "test-task"
                assert task["status"] == "RUNNING"

            # Validate schema for all tasks
            if "name" in task and task["name"] is not None:
                assert isinstance(task["name"], str)
            if "status" in task and task["status"] is not None:
                assert task["status"] in [
                    "CANCELED",
                    "COMPLETED",
                    "FAILED",
                    "RUNNING",
                    "TERMINATED",
                    "TIMED_OUT",
                ]

        assert found_test_task, "Test task should be present in the list"

    async def test_list_tasks_with_agent_id_filter(
        self, isolated_client, isolated_repositories
    ):
        """Test that list tasks endpoint filters by agent_id correctly"""

        agent_repo = isolated_repositories["agent_repository"]
        agents = [
            AgentEntity(
                id=orm_id(),
                name="test-agent-1",
                description="Test agent for integration testing",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            ),
            AgentEntity(
                id=orm_id(),
                name="test-agent-2",
                description="Test agent for integration testing",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            ),
        ]
        for agent in agents:
            await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]

        # Create a task directly in the PostgreSQL repository
        agent_one_task = TaskEntity(
            id=orm_id(),
            name="test-task-1",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )
        agent_two_task = TaskEntity(
            id=orm_id(),
            name="test-task-2",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )

        await task_repo.create(agent_id=agents[0].id, task=agent_one_task)
        await task_repo.create(agent_id=agents[1].id, task=agent_two_task)

        # When - Request tasks filtered by agent_id
        response_one = await isolated_client.get(f"/tasks?agent_id={agents[0].id}")
        response_two = await isolated_client.get(f"/tasks?agent_id={agents[1].id}")

        # Then - Should return tasks only for the specified agent
        assert response_one.status_code == 200
        assert response_two.status_code == 200

        tasks_one = response_one.json()
        tasks_two = response_two.json()

        assert len(tasks_one) == 1
        assert len(tasks_two) == 1

        assert tasks_one[0]["id"] == agent_one_task.id
        assert tasks_two[0]["id"] == agent_two_task.id

    async def test_list_tasks_with_agent_name_filter(
        self, isolated_client, isolated_repositories
    ):
        """Test that list tasks endpoint filters by agent_name correctly"""

        agent_repo = isolated_repositories["agent_repository"]
        agents = [
            AgentEntity(
                id=orm_id(),
                name="test-agent-alpha",
                description="Test agent for integration testing",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            ),
            AgentEntity(
                id=orm_id(),
                name="test-agent-beta",
                description="Test agent for integration testing",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            ),
        ]
        for agent in agents:
            await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]

        # Create tasks for each agent
        alpha_task = TaskEntity(
            id=orm_id(),
            name="test-task-alpha",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )
        beta_task = TaskEntity(
            id=orm_id(),
            name="test-task-beta",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )

        await task_repo.create(agent_id=agents[0].id, task=alpha_task)
        await task_repo.create(agent_id=agents[1].id, task=beta_task)

        # When - Request tasks filtered by agent_name
        response_alpha = await isolated_client.get(
            f"/tasks?agent_name={agents[0].name}"
        )
        response_beta = await isolated_client.get(f"/tasks?agent_name={agents[1].name}")

        # Then - Should return tasks only for the specified agent
        assert response_alpha.status_code == 200
        assert response_beta.status_code == 200

        tasks_alpha = response_alpha.json()
        tasks_beta = response_beta.json()

        assert len(tasks_alpha) == 1
        assert len(tasks_beta) == 1

        assert tasks_alpha[0]["id"] == alpha_task.id
        assert tasks_beta[0]["id"] == beta_task.id

    async def test_list_tasks_with_both_agent_id_and_agent_name_filter(
        self, isolated_client, isolated_repositories
    ):
        """Test that list tasks endpoint filters by both agent_id and agent_name correctly"""

        agent_repo = isolated_repositories["agent_repository"]
        target_agent = AgentEntity(
            id=orm_id(),
            name="target-agent",
            description="Target agent for filtering test",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        other_agent = AgentEntity(
            id=orm_id(),
            name="other-agent",
            description="Other agent for filtering test",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )

        await agent_repo.create(target_agent)
        await agent_repo.create(other_agent)

        task_repo = isolated_repositories["task_repository"]

        # Create tasks for each agent
        target_task = TaskEntity(
            id=orm_id(),
            name="target-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )
        other_task = TaskEntity(
            id=orm_id(),
            name="other-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
        )

        await task_repo.create(agent_id=target_agent.id, task=target_task)
        await task_repo.create(agent_id=other_agent.id, task=other_task)

        # When - Request tasks filtered by both agent_id and agent_name
        response = await isolated_client.get(
            f"/tasks?agent_id={target_agent.id}&agent_name={target_agent.name}"
        )

        # Then - Should return tasks only for the agent matching both criteria
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 1
        assert tasks[0]["id"] == target_task.id

    #
    async def test_get_task_by_id_returns_correct_task(
        self, isolated_client, test_task
    ):
        """Test getting a specific task by ID returns correct data"""
        # When - Get the test task by ID
        response = await isolated_client.get(f"/tasks/{test_task.id}")

        # Then - Should return the correct task with schema validation
        assert response.status_code == 200
        task_data = response.json()

        # Validate returned task matches our test task
        assert task_data["id"] == test_task.id
        assert task_data["name"] == "test-task"
        assert task_data["status"] == "RUNNING"

    #
    async def test_get_task_by_name_returns_correct_task(
        self, isolated_client, test_task
    ):
        """Test getting a specific task by name returns correct data"""
        # When - Get the test task by name
        response = await isolated_client.get("/tasks/name/test-task")

        # Then - Should return the correct task with schema validation
        assert response.status_code == 200
        task_data = response.json()

        # Validate returned task matches our test task
        assert task_data["id"] == test_task.id
        assert task_data["name"] == "test-task"
        assert task_data["status"] == "RUNNING"

    #
    async def test_get_task_non_existent_returns_404(self, isolated_client):
        """Test getting a non-existent task returns proper 404"""
        # When - Get a non-existent task
        response = await isolated_client.get("/tasks/non-existent-task-id")

        # Then - Should return 404 with proper error message
        assert response.status_code == 404
        error_data = response.json()
        assert "does not exist" in error_data["message"]

    #
    async def test_get_task_by_name_non_existent_returns_404(self, isolated_client):
        """Test getting task by name for non-existent task returns 404"""
        # When - Get a non-existent task by name
        response = await isolated_client.get("/tasks/name/non-existent-task-name")

        # Then - Should return 404
        assert response.status_code == 404

    #
    async def test_list_tasks_includes_params_in_response(
        self, isolated_client, test_task_with_params
    ):
        """Test that list tasks endpoint includes params field in response"""
        # When - Request all tasks
        response = await isolated_client.get("/tasks")

        # Then - Should succeed and include params in response
        assert response.status_code == 200
        tasks = response.json()
        assert isinstance(tasks, list)

        # Find our test task with params
        params_task = next(
            (task for task in tasks if task["id"] == test_task_with_params.id), None
        )
        assert params_task is not None, "Task with params should be in the list"

        # Verify params field exists and has correct structure
        assert "params" in params_task
        assert params_task["params"] is not None
        assert params_task["params"]["model"] == "gpt-4"
        assert params_task["params"]["temperature"] == 0.8
        assert params_task["params"]["max_tokens"] == 2000
        assert params_task["params"]["nested"]["setting"] == "value"
        assert params_task["params"]["nested"]["numbers"] == [1, 2, 3]

    #
    async def test_get_task_by_id_includes_params_in_response(
        self, isolated_client, test_task_with_params
    ):
        """Test that get task by ID includes params field in response"""
        # When - Get the test task with params by ID
        response = await isolated_client.get(f"/tasks/{test_task_with_params.id}")

        # Then - Should return the task with params
        assert response.status_code == 200
        task_data = response.json()

        # Verify task basic info
        assert task_data["id"] == test_task_with_params.id
        assert task_data["name"] == "test-task-with-params"
        assert task_data["status"] == "RUNNING"

        # Verify params field exists and has correct data
        assert "params" in task_data
        assert task_data["params"] is not None
        assert task_data["params"]["model"] == "gpt-4"
        assert task_data["params"]["temperature"] == 0.8
        assert task_data["params"]["max_tokens"] == 2000
        assert task_data["params"]["nested"]["setting"] == "value"
        assert task_data["params"]["nested"]["numbers"] == [1, 2, 3]

    #
    async def test_get_task_by_name_includes_params_in_response(
        self, isolated_client, test_task_with_params
    ):
        """Test that get task by name includes params field in response"""
        # When - Get the test task with params by name
        response = await isolated_client.get("/tasks/name/test-task-with-params")

        # Then - Should return the task with params
        assert response.status_code == 200
        task_data = response.json()

        # Verify task basic info
        assert task_data["id"] == test_task_with_params.id
        assert task_data["name"] == "test-task-with-params"
        assert task_data["status"] == "RUNNING"

        # Verify params field exists and has correct data
        assert "params" in task_data
        assert task_data["params"] is not None
        assert task_data["params"]["model"] == "gpt-4"
        assert task_data["params"]["temperature"] == 0.8
        assert task_data["params"]["max_tokens"] == 2000
        assert task_data["params"]["nested"]["setting"] == "value"
        assert task_data["params"]["nested"]["numbers"] == [1, 2, 3]

    #
    async def test_list_tasks_handles_null_params_correctly(
        self, isolated_client, test_task
    ):
        """Test that list tasks handles tasks with null params correctly"""
        # When - Request all tasks (test_task has null params)
        response = await isolated_client.get("/tasks")

        # Then - Should succeed and handle null params
        assert response.status_code == 200
        tasks = response.json()

        # Find our test task without params
        null_params_task = next(
            (task for task in tasks if task["id"] == test_task.id), None
        )
        assert null_params_task is not None

        # Verify params field exists and is null
        assert "params" in null_params_task
        assert null_params_task["params"] is None

    #
    async def test_get_task_by_id_handles_null_params_correctly(
        self, isolated_client, test_task
    ):
        """Test that get task by ID handles null params correctly"""
        # When - Get the test task without params by ID
        response = await isolated_client.get(f"/tasks/{test_task.id}")

        # Then - Should return the task with null params
        assert response.status_code == 200
        task_data = response.json()

        # Verify basic task info
        assert task_data["id"] == test_task.id
        assert task_data["name"] == "test-task"

        # Verify params field exists and is null
        assert "params" in task_data
        assert task_data["params"] is None

    async def test_update_task_endpoint_success(
        self, isolated_client, isolated_repositories
    ):
        """Test PUT /tasks/{task_id} with valid payload"""
        # Given - Create test agent and task via repository
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="metadata-update-agent",
            description="Agent for metadata update testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="task-for-metadata-update",
            status=TaskStatus.RUNNING,
            status_reason="Test task for metadata update endpoint",
            task_metadata={"initial": "metadata", "version": 1},
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When - Call update metadata endpoint with valid task_metadata
        update_payload = {
            "task_metadata": {
                "workflow": {
                    "stage": "updated",
                    "priority": "high",
                    "assignee": "api-test-user",
                },
                "configuration": {
                    "version": "2.0.0",
                    "environment": "integration",
                    "settings": {"timeout": 3000, "retries": 5, "debug": True},
                },
                "tags": ["api-test", "metadata-update", "integration"],
                "metrics": {
                    "started_at": "2024-01-01T10:00:00Z",
                    "estimated_duration": 1800.5,
                    "complexity_score": 75,
                },
            }
        }

        response = await isolated_client.put(
            f"/tasks/{created_task.id}", json=update_payload
        )

        # Then - Verify 200 response with updated task
        assert response.status_code == 200
        response_data = response.json()

        # Verify response includes updated task_metadata
        assert response_data["id"] == created_task.id
        assert response_data["name"] == "task-for-metadata-update"
        assert response_data["task_metadata"] == update_payload["task_metadata"]
        assert response_data["task_metadata"]["workflow"]["stage"] == "updated"
        assert response_data["task_metadata"]["configuration"]["version"] == "2.0.0"
        assert response_data["task_metadata"]["metrics"]["complexity_score"] == 75

    async def test_update_task_endpoint_validation(
        self, isolated_client, isolated_repositories
    ):
        """Test PUT /tasks/{task_id} with various payload types"""
        # Given - Create test agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="validation-test-agent",
            description="Agent for validation testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="validation-test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task for validation",
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # Test Case 1: Valid complex nested task_metadata structure
        complex_payload = {
            "task_metadata": {
                "application": {
                    "name": "ComplexApp",
                    "version": "3.2.1",
                    "components": [
                        {
                            "name": "frontend",
                            "technology": "React",
                            "version": "18.0.0",
                            "config": {
                                "port": 3000,
                                "hot_reload": True,
                                "build_optimization": False,
                            },
                        }
                    ],
                },
                "deployment": {
                    "environments": ["dev", "staging", "prod"],
                    "regions": {"primary": "us-west-2", "backup": "us-east-1"},
                    "scaling": {
                        "min_instances": 2,
                        "max_instances": 10,
                        "target_cpu_percent": 70.5,
                    },
                },
            }
        }
        response = await isolated_client.put(
            f"/tasks/{created_task.id}", json=complex_payload
        )
        assert response.status_code == 200
        assert response.json()["task_metadata"] == complex_payload["task_metadata"]

        # Test Case 2: Empty dictionary
        empty_payload = {"task_metadata": {}}
        response = await isolated_client.put(
            f"/tasks/{created_task.id}", json=empty_payload
        )
        assert response.status_code == 200
        assert response.json()["task_metadata"] == {}

        # Test Case 3: Various data types
        data_types_payload = {
            "task_metadata": {
                "string_field": "test string",
                "integer_field": 42,
                "float_field": 3.14159,
                "boolean_true": True,
                "boolean_false": False,
                "null_field": None,
                "array_strings": ["item1", "item2", "item3"],
                "array_numbers": [1, 2, 3, 4.5],
                "array_mixed": [1, "two", True, None],
                "nested_object": {"level1": {"level2": {"deep_value": "found"}}},
            }
        }
        response = await isolated_client.put(
            f"/tasks/{created_task.id}", json=data_types_payload
        )
        assert response.status_code == 200
        response_data = response.json()["task_metadata"]
        assert response_data["string_field"] == "test string"
        assert response_data["integer_field"] == 42
        assert response_data["float_field"] == 3.14159
        assert response_data["boolean_true"] is True
        assert response_data["boolean_false"] is False
        assert response_data["null_field"] is None
        assert (
            response_data["nested_object"]["level1"]["level2"]["deep_value"] == "found"
        )

    async def test_update_task_nonexistent_task(self, isolated_client):
        """Test PUT /tasks/{invalid_id} returns 404"""
        # Given - Non-existent task ID
        nonexistent_task_id = orm_id()  # Generate a valid UUID that doesn't exist
        update_payload = {"task_metadata": {"test": "data"}}

        # When - Call endpoint with non-existent task ID
        response = await isolated_client.put(
            f"/tasks/{nonexistent_task_id}", json=update_payload
        )

        # Then - Verify 404 response with proper error message
        assert response.status_code == 404
        error_data = response.json()
        assert (
            "does not exist" in error_data["message"]
            or "not found" in error_data["message"].lower()
        )

    async def test_update_task_invalid_request_body(
        self, isolated_client, isolated_repositories
    ):
        """Test PUT /tasks/{task_id} with invalid request body"""
        # Given - Create valid task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="invalid-body-test-agent",
            description="Agent for invalid body testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="invalid-body-test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test task for invalid body testing",
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # Test Case 1: Should not update non-mutable fields
        response = await isolated_client.put(
            f"/tasks/{created_task.id}",
            json={
                "id": orm_id(),
                "name": "should-not-be-used",
                "status": TaskStatus.FAILED,
            },
        )
        assert response.status_code == 200  # Should succeed with empty metadata
        response_data = response.json()
        assert response_data.get("task_metadata", None) is None
        # Verify other fields unchanged
        assert response_data["id"] == created_task.id
        assert response_data["name"] == created_task.name
        assert response_data["status"] == "RUNNING"

        # Test Case 3: Invalid JSON structure (should be handled by FastAPI)
        response = await isolated_client.put(
            f"/tasks/{created_task.id}",
            data="invalid json content",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422  # JSON decode error

    async def test_update_task_by_name_endpoint_success(
        self, isolated_client, isolated_repositories
    ):
        """Test PUT /tasks/name/{task_name} with valid payload"""
        # Given - Create test agent and task via repository
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="metadata-update-by-name-agent",
            description="Agent for metadata update by name testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="task-for-metadata-update-by-name",
            status=TaskStatus.RUNNING,
            status_reason="Test task for metadata update by name endpoint",
            task_metadata={"initial": "metadata", "version": 1},
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When - Call update metadata by name endpoint with valid task_metadata
        update_payload = {
            "task_metadata": {
                "workflow": {
                    "stage": "updated_by_name",
                    "priority": "high",
                    "assignee": "api-test-user",
                },
                "configuration": {
                    "version": "2.0.0",
                    "environment": "integration",
                    "settings": {"timeout": 3000, "retries": 5, "debug": True},
                },
                "tags": ["api-test", "metadata-update", "by-name", "integration"],
                "metrics": {
                    "started_at": "2024-01-01T10:00:00Z",
                    "estimated_duration": 1800.5,
                    "complexity_score": 75,
                },
            }
        }

        response = await isolated_client.put(
            f"/tasks/name/{created_task.name}", json=update_payload
        )

        # Then - Verify 200 response with updated task
        assert response.status_code == 200
        response_data = response.json()

        # Verify response includes updated task_metadata
        assert response_data["id"] == created_task.id
        assert response_data["name"] == "task-for-metadata-update-by-name"
        assert response_data["task_metadata"] == update_payload["task_metadata"]
        assert response_data["task_metadata"]["workflow"]["stage"] == "updated_by_name"
        assert response_data["task_metadata"]["configuration"]["version"] == "2.0.0"
        assert response_data["task_metadata"]["metrics"]["complexity_score"] == 75

    async def test_list_tasks_includes_task_metadata_field(
        self, isolated_client, isolated_repositories
    ):
        """Test GET /tasks includes task_metadata in response"""
        # Given - Create task with task_metadata via repository
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="list-metadata-agent",
            description="Agent for list metadata testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task_metadata = {
            "list_test": {
                "category": "integration",
                "priority": "medium",
                "features": ["api", "metadata", "list"],
            },
            "configuration": {"timeout": 5000, "retries": 3, "environment": "test"},
            "created_by": "integration_test",
            "version": 1.0,
        }

        task = TaskEntity(
            id=orm_id(),
            name="task-with-metadata-for-list",
            status=TaskStatus.RUNNING,
            status_reason="Task with metadata for list testing",
            task_metadata=task_metadata,
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When - Call list endpoint
        response = await isolated_client.get("/tasks")

        # Then - Verify task_metadata field present in response
        assert response.status_code == 200
        tasks = response.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1

        # Find our test task and verify task_metadata structure matches created data
        test_task = next((t for t in tasks if t["id"] == created_task.id), None)
        assert test_task is not None
        assert "task_metadata" in test_task
        assert test_task["task_metadata"] == task_metadata
        assert test_task["task_metadata"]["list_test"]["category"] == "integration"
        assert test_task["task_metadata"]["configuration"]["timeout"] == 5000
        assert test_task["task_metadata"]["version"] == 1.0

    async def test_get_task_by_id_includes_task_metadata_field(
        self, isolated_client, isolated_repositories
    ):
        """Test GET /tasks/{task_id} includes task_metadata"""
        # Given - Create task with task_metadata via repository
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="get-by-id-metadata-agent",
            description="Agent for get by ID metadata testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task_metadata = {
            "get_by_id_test": {
                "endpoint": "/tasks/{id}",
                "method": "GET",
                "expected_fields": ["id", "name", "status", "task_metadata"],
            },
            "data_validation": {
                "string_value": "test_string",
                "numeric_value": 123.45,
                "boolean_value": True,
                "array_value": [1, 2, 3],
                "null_value": None,
            },
        }

        task = TaskEntity(
            id=orm_id(),
            name="task-for-get-by-id-metadata",
            status=TaskStatus.COMPLETED,
            status_reason="Task for get by ID metadata testing",
            task_metadata=task_metadata,
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When - Retrieve task by ID
        response = await isolated_client.get(f"/tasks/{created_task.id}")

        # Then - Verify task_metadata field in response and verify task_metadata matches created data
        assert response.status_code == 200
        task_data = response.json()

        assert task_data["id"] == created_task.id
        assert task_data["name"] == "task-for-get-by-id-metadata"
        assert task_data["status"] == "COMPLETED"
        assert "task_metadata" in task_data
        assert task_data["task_metadata"] == task_metadata
        assert task_data["task_metadata"]["get_by_id_test"]["endpoint"] == "/tasks/{id}"
        assert task_data["task_metadata"]["data_validation"]["numeric_value"] == 123.45

    async def test_get_task_by_name_includes_task_metadata_field(
        self, isolated_client, isolated_repositories
    ):
        """Test GET /tasks/name/{task_name} includes task_metadata"""
        # Given - Create task with task_metadata via repository
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="get-by-name-metadata-agent",
            description="Agent for get by name metadata testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task_metadata = {
            "get_by_name_test": {
                "endpoint": "/tasks/name/{name}",
                "method": "GET",
                "test_name": "task-for-get-by-name-metadata",
            },
            "retrieval_info": {
                "indexed_by": "name",
                "unique_constraint": True,
                "case_sensitive": True,
            },
        }

        task = TaskEntity(
            id=orm_id(),
            name="task-for-get-by-name-metadata",
            status=TaskStatus.FAILED,
            status_reason="Task for get by name metadata testing",
            task_metadata=task_metadata,
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When - Retrieve task by name
        response = await isolated_client.get(f"/tasks/name/{created_task.name}")

        # Then - Verify task_metadata field in response
        assert response.status_code == 200
        task_data = response.json()

        assert task_data["id"] == created_task.id
        assert task_data["name"] == "task-for-get-by-name-metadata"
        assert task_data["status"] == "FAILED"
        assert "task_metadata" in task_data
        assert task_data["task_metadata"] == task_metadata
        assert (
            task_data["task_metadata"]["get_by_name_test"]["test_name"]
            == "task-for-get-by-name-metadata"
        )

    async def test_list_tasks_handles_null_task_metadata_correctly(
        self, isolated_client, isolated_repositories
    ):
        """Test GET /tasks correctly handles tasks with null task_metadata"""
        # Given - Create task with task_metadata=None via repository
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="null-metadata-list-agent",
            description="Agent for null metadata list testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="task-with-null-metadata-list",
            status=TaskStatus.RUNNING,
            status_reason="Task with null metadata for list testing",
            task_metadata=None,
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When - Call list endpoint
        response = await isolated_client.get("/tasks")

        # Then - Verify list endpoint returns task_metadata: null
        assert response.status_code == 200
        tasks = response.json()

        # Find our test task
        test_task = next((t for t in tasks if t["id"] == created_task.id), None)
        assert test_task is not None
        assert "task_metadata" in test_task
        assert test_task["task_metadata"] is None

    async def test_get_task_endpoints_handle_null_task_metadata(
        self, isolated_client, isolated_repositories
    ):
        """Test GET endpoints handle null task_metadata correctly"""
        # Given - Create task with task_metadata=None
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="null-metadata-get-agent",
            description="Agent for null metadata get testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="task-with-null-metadata-get",
            status=TaskStatus.TERMINATED,
            status_reason="Task with null metadata for get testing",
            task_metadata=None,
        )
        created_task = await task_repo.create(agent_id=agent.id, task=task)

        # When & Then - Verify GET by ID returns task_metadata: null
        response_by_id = await isolated_client.get(f"/tasks/{created_task.id}")
        assert response_by_id.status_code == 200
        task_data_by_id = response_by_id.json()
        assert "task_metadata" in task_data_by_id
        assert task_data_by_id["task_metadata"] is None
        assert task_data_by_id["id"] == created_task.id

        # When & Then - Verify GET by name returns task_metadata: null
        response_by_name = await isolated_client.get(f"/tasks/name/{created_task.name}")
        assert response_by_name.status_code == 200
        task_data_by_name = response_by_name.json()
        assert "task_metadata" in task_data_by_name
        assert task_data_by_name["task_metadata"] is None
        assert task_data_by_name["name"] == created_task.name
