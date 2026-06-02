"""
Integration tests for message-route authorization.

Covers the AGX1-277 deliverable: list/get messages enforce ``task.read`` on
the parent task, with denied checks collapsing to 404 (not 403) so callers
cannot probe cross-tenant existence by comparing response codes.
"""

from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from src.adapters.authorization.exceptions import AuthorizationError
from src.api.schemas.authorization_types import AgentexResourceType
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.task_messages import TaskMessageEntity, TextContentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id

MOCK_PRINCIPAL_CONTEXT = {
    "account_id": "test-account-id",
    "user_id": "test-user-id",
}


def _mock_post_factory(*, deny_task_ids: set[str] | None = None):
    """Return a side_effect that allows authn + authz, except for tasks listed
    in ``deny_task_ids`` for which ``/v1/authz/check`` raises AuthorizationError.
    """
    deny_task_ids = deny_task_ids or set()

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
            if (
                resource.get("type") == AgentexResourceType.task.value
                and resource.get("selector") in deny_task_ids
            ):
                raise AuthorizationError("Denied by mock")
            return {"allowed": True}
        if path == "/v1/authz/search":
            return {"items": []}
        raise Exception(f"Unknown path: {path}")

    return _side_effect


@pytest.mark.integration
class TestMessagesAuthzAPIIntegration:
    """End-to-end integration tests for message-route authorization."""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-authz-agent",
            description="Agent for message-authz tests",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task(self, isolated_repositories, test_agent):
        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="test-authz-task",
            status=TaskStatus.RUNNING,
            status_reason="Task for message-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_message(self, isolated_repositories, test_task):
        message_repo = isolated_repositories["task_message_repository"]
        message = TaskMessageEntity(
            id=orm_id(),
            task_id=test_task.id,
            content=TextContentEntity(type="text", author="user", content="hello"),
            streaming_status="DONE",
        )
        return await message_repo.create(message)

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_factory(),
    )
    async def test_get_message_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_message,
        test_task,
    ):
        response = await isolated_client.get(f"/messages/{test_message.id}")
        assert response.status_code == 200
        assert response.json()["id"] == test_message.id

        # Exactly one /v1/authz/check, on the parent task with the read operation.
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
        assert authz_data["principal"] == MOCK_PRINCIPAL_CONTEXT

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_get_message_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_message,
        test_task,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task.id}),
        ):
            response = await isolated_client.get(f"/messages/{test_message.id}")
        # Denial on the parent task must collapse to 404, not surface as 403.
        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_factory(),
    )
    async def test_get_message_nonexistent_returns_404(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
    ):
        response = await isolated_client.get(f"/messages/{orm_id()}")
        assert response.status_code == 404
        # The parent-task lookup raises ItemDoesNotExist before any authz check
        # fires, so /v1/authz/check should never be called.
        assert not any(
            call[0][1] == "/v1/authz/check"
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
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_factory(),
    )
    async def test_list_messages_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_message,
        test_task,
    ):
        response = await isolated_client.get(f"/messages?task_id={test_task.id}")
        assert response.status_code == 200
        body = response.json()
        assert any(m["id"] == test_message.id for m in body)

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
