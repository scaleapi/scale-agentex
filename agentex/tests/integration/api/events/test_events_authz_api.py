"""Tests for event route authorization — routes delegate checks to the parent agent."""

from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from src.adapters.authorization.exceptions import AuthorizationError
from src.api.schemas.authorization_types import AgentexResourceType
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.task_messages import TextContentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id

MOCK_PRINCIPAL_CONTEXT = {
    "account_id": "test-account-id",
    "user_id": "test-user-id",
}


def _mock_post_factory(
    *,
    deny_agent_ids: set[str] | None = None,
    deny_task_ids: set[str] | None = None,
):
    """Return a side_effect that allows authn + authz, except for agents/tasks
    listed in ``deny_*_ids`` for which ``/v1/authz/check`` raises
    AuthorizationError.
    """
    deny_agent_ids = deny_agent_ids or set()
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
                resource.get("type") == AgentexResourceType.agent.value
                and resource.get("selector") in deny_agent_ids
            ):
                raise AuthorizationError("Denied by mock")
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
class TestEventsAuthzAPIIntegration:
    """End-to-end integration tests for event-route authorization."""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-authz-agent",
            description="Agent for event-authz tests",
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
            status_reason="Task for event-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_event(self, isolated_repositories, test_agent, test_task):
        event_repo = isolated_repositories["event_repository"]
        content = TextContentEntity(type="text", author="user", content="hello")
        return await event_repo.create(
            id=orm_id(),
            task_id=test_task.id,
            agent_id=test_agent.id,
            content=content,
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
    async def test_get_event_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_event,
        test_agent,
    ):
        response = await isolated_client.get(f"/events/{test_event.id}")
        assert response.status_code == 200
        assert response.json()["id"] == test_event.id

        # One check, on the parent agent (not the task).
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.agent.value
        assert authz_data["resource"]["selector"] == test_agent.id
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
    async def test_get_event_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_event,
        test_agent,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_agent_ids={test_agent.id}),
        ):
            response = await isolated_client.get(f"/events/{test_event.id}")
        # Parent-agent denial collapses to 404.
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
    async def test_get_event_nonexistent_returns_404(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
    ):
        response = await isolated_client.get(f"/events/{orm_id()}")
        assert response.status_code == 404
        # Event lookup 404s before any authz call fires.
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
    async def test_list_events_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_event,
        test_agent,
        test_task,
    ):
        response = await isolated_client.get(
            f"/events?task_id={test_task.id}&agent_id={test_agent.id}"
        )
        assert response.status_code == 200
        body = response.json()
        assert any(e["id"] == test_event.id for e in body)

        # Two checks: one on the task, one on the agent.
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 2
        checked = {
            (
                call[1]["json"]["resource"]["type"],
                call[1]["json"]["resource"]["selector"],
            )
            for call in check_calls
        }
        assert (AgentexResourceType.task.value, test_task.id) in checked
        assert (AgentexResourceType.agent.value, test_agent.id) in checked
        for call in check_calls:
            assert call[1]["json"]["operation"] == "read"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_events_unauthorized_agent_returns_403(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_event,
        test_agent,
        test_task,
    ):
        """Direct-resource denials surface as 403 (convention from #249/#255)."""
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_agent_ids={test_agent.id}),
        ):
            response = await isolated_client.get(
                f"/events?task_id={test_task.id}&agent_id={test_agent.id}"
            )
        assert response.status_code == 403
