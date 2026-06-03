"""
Integration tests for state-route authorization.

States intentionally do not have their own AuthZ resource type. Every state
read or write is authorized through the parent task.
"""

from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from src.adapters.authorization.exceptions import AuthorizationError
from src.api.schemas.authorization_types import AgentexResourceType
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.states import StateEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id

MOCK_PRINCIPAL_CONTEXT = {
    "account_id": "test-account-id",
    "user_id": "test-user-id",
}


def _mock_post_factory(
    *,
    accessible_task_ids: set[str] | None = None,
    denied_task_operations: dict[str, set[str]] | None = None,
):
    """Return a side_effect for authn + authz.

    ``accessible_task_ids`` controls ``/v1/authz/search`` for task read access.
    ``denied_task_operations`` controls task ``/v1/authz/check`` denials by
    task id and operation literal.
    """
    accessible_task_ids = accessible_task_ids or set()
    denied_task_operations = denied_task_operations or {}

    async def _side_effect(
        base_url: str = "http://test.com",
        path: str = "/test",
        *,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if path == "/v1/authn":
            return MOCK_PRINCIPAL_CONTEXT
        if path == "/v1/authz/check":
            assert json is not None
            resource = json.get("resource", {})
            operation = json.get("operation")
            if (
                resource.get("type") == AgentexResourceType.task.value
                and operation
                in denied_task_operations.get(resource.get("selector"), set())
            ):
                raise AuthorizationError("Denied by mock")
            return {"allowed": True}
        if path == "/v1/authz/search":
            assert json is not None
            assert json["filter_resource"] == AgentexResourceType.task.value
            assert json["filter_operation"] == "read"
            return {"items": list(accessible_task_ids)}
        if path == "/v1/authz/register":
            raise AssertionError("states must not be registered as authz resources")
        raise Exception(f"Unknown path: {path}")

    return _side_effect


@pytest.mark.integration
class TestStatesAuthzAPIIntegration:
    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-state-authz-agent",
            description="Agent for state-authz tests",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task(self, isolated_repositories, test_agent):
        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="test-state-authz-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for state-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def other_task(self, isolated_repositories, test_agent):
        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="other-state-authz-task",
            status=TaskStatus.RUNNING,
            status_reason="Other task for state-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_state(self, isolated_repositories, test_task, test_agent):
        state_repo = isolated_repositories["task_state_repository"]
        state = StateEntity(
            id=orm_id(),
            task_id=test_task.id,
            agent_id=test_agent.id,
            state={"visible": True},
        )
        return await state_repo.create(state)

    @pytest_asyncio.fixture
    async def other_state(self, isolated_repositories, other_task, test_agent):
        state_repo = isolated_repositories["task_state_repository"]
        state = StateEntity(
            id=orm_id(),
            task_id=other_task.id,
            agent_id=test_agent.id,
            state={"visible": False},
        )
        return await state_repo.create(state)

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_user_with_task_view_but_not_owner_cannot_create_state(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_task,
        test_agent,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(
                accessible_task_ids={test_task.id},
                denied_task_operations={test_task.id: {"manage_access"}},
            ),
        ) as post_with_error_handling_mock:
            response = await isolated_client.post(
                "/states",
                json={
                    "task_id": test_task.id,
                    "agent_id": test_agent.id,
                    "state": {"blocked": True},
                },
            )

        # Denied parent-task checks collapse to 404 so task ids cannot be
        # probed through the states API.
        assert response.status_code == 404
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task.id
        # AGX1-237 exposes manage_access as an owner-only task permission.
        assert authz_data["operation"] == "manage_access"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_user_without_task_view_cannot_list_or_get_state(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_state,
        test_task,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(
                accessible_task_ids=set(),
                denied_task_operations={test_task.id: {"read"}},
            ),
        ):
            list_response = await isolated_client.get(
                "/states", params={"task_id": test_task.id}
            )
            get_response = await isolated_client.get(f"/states/{test_state.id}")

        # Explicit task-id list and GET denials on the parent task must
        # collapse to 404, not 403.
        assert list_response.status_code == 404
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_states_with_task_id_checks_that_task_directly(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_state,
        test_task,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(accessible_task_ids=set()),
        ) as post_with_error_handling_mock:
            response = await isolated_client.get(
                "/states", params={"task_id": test_task.id}
            )

        assert response.status_code == 200
        assert [state["id"] for state in response.json()] == [test_state.id]
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task.id
        assert authz_data["operation"] == "read"
        assert not any(
            call[0][1] == "/v1/authz/search"
            for call in post_with_error_handling_mock.call_args_list
        )

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_states_filters_to_tasks_the_user_can_view(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_state,
        other_state,
        test_task,
        other_task,
        test_agent,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(
                accessible_task_ids={test_task.id},
                denied_task_operations={other_task.id: {"read"}},
            ),
        ):
            response = await isolated_client.get(
                "/states", params={"agent_id": test_agent.id}
            )
            denied_task_response = await isolated_client.get(
                "/states", params={"task_id": other_task.id}
            )

        assert response.status_code == 200
        body = response.json()
        assert [state["id"] for state in body] == [test_state.id]
        assert denied_task_response.status_code == 404

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_user_with_task_view_but_not_owner_cannot_update_state(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_state,
        test_task,
        test_agent,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(
                accessible_task_ids={test_task.id},
                denied_task_operations={test_task.id: {"manage_access"}},
            ),
        ) as post_with_error_handling_mock:
            response = await isolated_client.put(
                f"/states/{test_state.id}",
                json={
                    "task_id": test_task.id,
                    "agent_id": test_agent.id,
                    "state": {"blocked": True},
                },
            )

        assert response.status_code == 404
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task.id
        assert authz_data["operation"] == "manage_access"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_user_without_task_delete_cannot_delete_state(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_state,
        test_task,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(
                accessible_task_ids={test_task.id},
                denied_task_operations={test_task.id: {"delete"}},
            ),
        ) as post_with_error_handling_mock:
            response = await isolated_client.delete(f"/states/{test_state.id}")

        assert response.status_code == 404
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task.id
        assert authz_data["operation"] == "delete"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_task_owner_can_create_state(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_task,
        test_agent,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(accessible_task_ids={test_task.id}),
        ) as post_with_error_handling_mock:
            response = await isolated_client.post(
                "/states",
                json={
                    "task_id": test_task.id,
                    "agent_id": test_agent.id,
                    "state": {"created": True},
                },
            )

        assert response.status_code == 200
        assert response.json()["task_id"] == test_task.id
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        assert check_calls[0][1]["json"]["operation"] == "manage_access"
        assert not any(
            call[0][1] == "/v1/authz/register"
            for call in post_with_error_handling_mock.call_args_list
        )
