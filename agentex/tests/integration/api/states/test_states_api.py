"""
Integration tests for state endpoints following FastAPI async testing best practices.
Tests the full HTTP request → FastAPI → response cycle with API-first validation.
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.states import StateEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestStatesAPIIntegration:
    """Integration tests for state endpoints using API-first validation"""

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
    async def test_agent_2(self, isolated_repositories):
        """Create a test agent for task creation"""
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-agent-2",
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
            params=None,
            task_metadata=None,
            created_at=None,
            updated_at=None,
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_task_2(self, isolated_repositories, test_agent):
        """Create a test task directly via repository (bypass service MongoDB dependency)"""
        task_repo = isolated_repositories["task_repository"]

        # Create a task directly in the PostgreSQL repository
        task = TaskEntity(
            id=orm_id(),
            name="test-task-2",
            status=TaskStatus.RUNNING,
            status_reason="Test task created for integration testing",
            params=None,
            task_metadata=None,
            created_at=None,
            updated_at=None,
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_pagination_states(
        self, isolated_repositories, test_task, test_agent
    ):
        """Create a test state using the repository"""
        state_repo = isolated_repositories["task_state_repository"]
        states = []
        for i in range(60):
            state = StateEntity(
                id=orm_id(),
                task_id=test_task.id,
                agent_id=test_agent.id,
                state={"test": "test", "key": f"value-{i}"},
            )
            states.append(await state_repo.create(state))
        return states

    async def test_listing_states(
        self, isolated_client, test_task, test_agent, test_task_2, test_agent_2
    ):
        for task in [test_task, test_task_2]:
            for agent in [test_agent, test_agent_2]:
                state_value = {"task_id": task.id, "agent_id": agent.id}
                state_data = {
                    "task_id": task.id,
                    "agent_id": agent.id,
                    "state": state_value,
                }

                # When - Create state via POST
                create_response = await isolated_client.post("/states", json=state_data)
                assert create_response.status_code == 200

        """Test listing states"""
        # When - List states
        response = await isolated_client.get("/states")
        # Then - Should return 200
        assert response.status_code == 200
        assert len(response.json()) == 4

        response = await isolated_client.get(
            "/states", params={"task_id": test_task.id}
        )
        # Then - Should return 200
        assert response.status_code == 200
        response_json = response.json()
        assert len(response_json) == 2
        assert {state["task_id"] for state in response_json} == {test_task.id}
        assert {state["agent_id"] for state in response_json} == {
            test_agent.id,
            test_agent_2.id,
        }

        response = await isolated_client.get(
            "/states", params={"agent_id": test_agent.id}
        )
        # Then - Should return 200
        assert response.status_code == 200
        response_json = response.json()
        assert len(response_json) == 2
        assert {state["task_id"] for state in response_json} == {
            test_task.id,
            test_task_2.id,
        }
        assert {state["agent_id"] for state in response_json} == {test_agent.id}

        response = await isolated_client.get(
            "/states", params={"task_id": test_task.id, "agent_id": test_agent.id}
        )
        # Then - Should return 200
        assert response.status_code == 200
        response_json = response.json()
        assert len(response_json) == 1
        assert response_json[0]["task_id"] == test_task.id
        assert response_json[0]["agent_id"] == test_agent.id

    async def test_create_and_retrieve_state_consistency(
        self, isolated_client, test_agent, test_task
    ):
        """Test state creation and validate POST → GET consistency (API-first)"""
        # Given - State creation data
        state_value = {"test": "test", "key": "value"}
        state_data = {
            "task_id": test_task.id,
            "agent_id": test_agent.id,
            "state": state_value,
        }

        # When - Create state via POST
        create_response = await isolated_client.post("/states", json=state_data)

        # Then - Should succeed and return created state
        assert create_response.status_code == 200
        created_state = create_response.json()

        # Validate response has required fields
        assert "id" in created_state
        assert created_state["task_id"] == state_data["task_id"]
        assert created_state["agent_id"] == state_data["agent_id"]
        assert created_state["state"] == state_value
        state_id = created_state["id"]

        # API-first validation: GET the created state
        get_response = await isolated_client.get(f"/states/{state_id}")
        assert get_response.status_code == 200
        retrieved_state = get_response.json()

        # Validate POST/GET consistency
        assert retrieved_state["id"] == state_id
        assert created_state["task_id"] == state_data["task_id"]
        assert created_state["agent_id"] == state_data["agent_id"]
        assert created_state["state"] == state_value

        # API-first validation: UPDATE with wrong task_id does nothing
        update_response = await isolated_client.put(
            f"/states/{state_id}",
            json={
                "state": {},
                "task_id": "some-other-task-id",
                "agent_id": test_agent.id,
            },
        )
        assert update_response.status_code == 200
        updated_state = update_response.json()

        assert updated_state["id"] == state_id
        assert updated_state["task_id"] == state_data["task_id"]
        assert updated_state["agent_id"] == state_data["agent_id"]
        assert updated_state["state"] == state_value

        # API-first validation: UPDATE the created state
        state_value_updated = {"test": "updated"}
        update_response = await isolated_client.put(
            f"/states/{state_id}",
            json={
                "state": state_value_updated,
                "task_id": test_task.id,
                "agent_id": test_agent.id,
            },
        )
        assert update_response.status_code == 200
        updated_state = update_response.json()

        assert updated_state["id"] == state_id
        assert updated_state["task_id"] == state_data["task_id"]
        assert updated_state["agent_id"] == state_data["agent_id"]
        assert updated_state["state"] == state_value_updated

        # API-first validation: DELETE the created state
        delete_response = await isolated_client.delete(f"/states/{state_id}")
        assert delete_response.status_code == 200
        deleted_state = delete_response.json()
        assert deleted_state["id"] == state_id
        assert deleted_state["task_id"] == state_data["task_id"]
        assert deleted_state["agent_id"] == state_data["agent_id"]
        assert deleted_state["state"] == state_value_updated

        list_response = await isolated_client.get("/states")
        assert list_response.status_code == 200
        list_states = list_response.json()
        assert len(list_states) == 0

    async def test_get_state_non_existent(self, isolated_client):
        """Test getting a non-existent state returns 404"""
        # When - Get a non-existent state
        response = await isolated_client.get("/states/4B95BB0000F372932B938B9B")

        # Then - Should return 404
        assert response.status_code == 404
        assert "does not exist" in response.json()["message"]

    async def test_delete_state_non_existent(self, isolated_client):
        """Test deleting a non-existent state returns 404"""
        # When - Get a non-existent state
        response = await isolated_client.delete("/states/4B95BB0000F372932B938B9B")

        # Then - Should return 404
        assert response.status_code == 404
        assert "does not exist" in response.json()["message"]

    async def test_list_states_pagination(
        self, isolated_client, test_pagination_states, test_task, test_agent
    ):
        """Test listing states with pagination"""
        # When - List states with pagination
        response = await isolated_client.get(
            "/states", params={"task_id": test_task.id, "agent_id": test_agent.id}
        )
        assert response.status_code == 200
        response_json = response.json()
        # Default limit if none specified
        assert len(response_json) == 50

        page_number = 1
        paginated_states = []
        while True:
            response = await isolated_client.get(
                "/states",
                params={
                    "limit": 7,
                    "page_number": page_number,
                    "task_id": test_task.id,
                    "agent_id": test_agent.id,
                },
            )
            assert response.status_code == 200
            states_data = response.json()
            paginated_states.extend(states_data)
            if len(states_data) < 1:
                break
            page_number += 1
        assert len(paginated_states) == len(test_pagination_states)
        assert {(d["id"], d["state"]["key"]) for d in paginated_states} == {
            (d.id, d.state["key"]) for d in test_pagination_states
        }

    async def test_list_states_with_order_by(
        self, isolated_client, isolated_repositories
    ):
        """Test that list states endpoint supports order_by parameter"""
        # Given - Create an agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="order-by-state-agent",
            description="Agent for order_by state testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="order-by-state-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for order_by state testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create multiple states
        state_repo = isolated_repositories["task_state_repository"]
        states = []
        for i in range(3):
            state = StateEntity(
                id=orm_id(),
                task_id=task.id,
                agent_id=agent.id,
                state={"order": i, "key": f"value-{i}"},
            )
            states.append(await state_repo.create(state))

        # When - Request states with order_by=created_at and order_direction=asc
        response_asc = await isolated_client.get(
            "/states",
            params={
                "task_id": task.id,
                "agent_id": agent.id,
                "order_by": "created_at",
                "order_direction": "asc",
            },
        )

        # Then - Should return states in ascending order
        assert response_asc.status_code == 200
        states_asc = response_asc.json()
        assert len(states_asc) == 3

        # Verify ascending order
        for i in range(len(states_asc) - 1):
            assert states_asc[i]["created_at"] <= states_asc[i + 1]["created_at"]

        # When - Request states with order_by=created_at and order_direction=desc
        response_desc = await isolated_client.get(
            "/states",
            params={
                "task_id": task.id,
                "agent_id": agent.id,
                "order_by": "created_at",
                "order_direction": "desc",
            },
        )

        # Then - Should return states in descending order
        assert response_desc.status_code == 200
        states_desc = response_desc.json()
        assert len(states_desc) == 3

        # Verify descending order
        for i in range(len(states_desc) - 1):
            assert states_desc[i]["created_at"] >= states_desc[i + 1]["created_at"]

        # Verify asc and desc return different orderings (first element of asc should be in last position of desc)
        # Note: We only check the first element reversal since items with identical timestamps
        # may have unpredictable relative ordering
        assert states_asc[0]["id"] == states_desc[-1]["id"]

    async def test_list_states_order_by_defaults_to_desc(
        self, isolated_client, isolated_repositories
    ):
        """Test that order_direction defaults to desc for states"""
        # Given - Create an agent and task
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="order-default-state-agent",
            description="Agent for order default state testing",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        await agent_repo.create(agent)

        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="order-default-state-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for order default state testing",
        )
        await task_repo.create(agent_id=agent.id, task=task)

        # Create multiple states
        state_repo = isolated_repositories["task_state_repository"]
        for i in range(3):
            state = StateEntity(
                id=orm_id(),
                task_id=task.id,
                agent_id=agent.id,
                state={"order": i},
            )
            await state_repo.create(state)

        # When - Request states with order_by but without order_direction
        response = await isolated_client.get(
            "/states",
            params={
                "task_id": task.id,
                "agent_id": agent.id,
                "order_by": "created_at",
            },
        )

        # Then - Should return states in descending order (default)
        assert response.status_code == 200
        states = response.json()
        assert len(states) == 3

        # Verify descending order
        for i in range(len(states) - 1):
            assert states[i]["created_at"] >= states[i + 1]["created_at"]
