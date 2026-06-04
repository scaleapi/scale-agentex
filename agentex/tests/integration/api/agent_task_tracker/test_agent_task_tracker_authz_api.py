"""Integration tests for agent_task_tracker route authorization."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from src.adapters.authorization.exceptions import AuthorizationError
from src.api.schemas.authorization_types import AgentexResourceType
from src.domain.entities.agent_task_tracker import AgentTaskTrackerEntity
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id

MOCK_PRINCIPAL_CONTEXT = {
    "account_id": "test-account-id",
    "user_id": "test-user-id",
}


def _mock_post_factory(
    *,
    deny_task_ids: set[str] | None = None,
    search_items: list[str] | None = None,
):
    """Return a side_effect that allows authn + authz, except for tasks listed
    in ``deny_task_ids`` for which ``/v1/authz/check`` raises AuthorizationError.

    ``/v1/authz/search`` (used by the list route's ``DAuthorizedResourceIds``)
    returns ``search_items`` as the set of authorized task ids.
    """
    deny_task_ids = deny_task_ids or set()
    search_items = search_items if search_items is not None else []

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
            return {"items": list(search_items)}
        raise Exception(f"Unknown path: {path}")

    return _side_effect


@pytest.mark.integration
class TestAgentTaskTrackerAuthzAPIIntegration:
    """End-to-end integration tests for tracker-route authorization."""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-authz-agent",
            description="Agent for tracker-authz tests",
            acp_url="http://test-acp:8000",
            acp_type=ACPType.SYNC,
        )
        return await agent_repo.create(agent)

    @pytest_asyncio.fixture
    async def test_task_a(self, isolated_repositories, test_agent):
        """Authorized task."""
        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="test-authz-task-a",
            status=TaskStatus.RUNNING,
            status_reason="Authorized task for tracker-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_task_b(self, isolated_repositories, test_agent):
        """Denied task."""
        task_repo = isolated_repositories["task_repository"]
        task = TaskEntity(
            id=orm_id(),
            name="test-authz-task-b",
            status=TaskStatus.RUNNING,
            status_reason="Denied task for tracker-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_tracker_a(self, isolated_repositories, test_agent, test_task_a):
        tracker_repo = isolated_repositories["agent_task_tracker_repository"]
        tracker = AgentTaskTrackerEntity(
            id=orm_id(),
            agent_id=test_agent.id,
            task_id=test_task_a.id,
            status="PROCESSING",
            status_reason="Tracker on authorized task",
            last_processed_event_id=None,
            created_at=datetime.now(UTC),
        )
        return await tracker_repo.create(tracker)

    @pytest_asyncio.fixture
    async def test_tracker_b(self, isolated_repositories, test_agent, test_task_b):
        tracker_repo = isolated_repositories["agent_task_tracker_repository"]
        tracker = AgentTaskTrackerEntity(
            id=orm_id(),
            agent_id=test_agent.id,
            task_id=test_task_b.id,
            status="PROCESSING",
            status_reason="Tracker on denied task",
            last_processed_event_id=None,
            created_at=datetime.now(UTC),
        )
        return await tracker_repo.create(tracker)

    # ── get ──

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
    async def test_get_tracker_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_task_a,
    ):
        response = await isolated_client.get(f"/tracker/{test_tracker_a.id}")
        assert response.status_code == 200
        assert response.json()["id"] == test_tracker_a.id

        # Exactly one /v1/authz/check, on the parent task with the read operation.
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task_a.id
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
    async def test_get_tracker_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_task_a,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task_a.id}),
        ):
            response = await isolated_client.get(f"/tracker/{test_tracker_a.id}")
        # Denial on the parent task must collapse to 404, not surface as 403.
        assert response.status_code == 404

    # ── list ──

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_filters_to_authorized_tasks(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_tracker_b,
        test_task_a,
        test_task_b,
    ):
        # Search authorizes only task A, so task B's tracker is silently dropped.
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(search_items=[test_task_a.id]),
        ):
            response = await isolated_client.get("/tracker")
        assert response.status_code == 200
        trackers = response.json()
        returned_task_ids = {t["task_id"] for t in trackers}
        # Only task A's trackers come back; task B's are excluded.
        assert returned_task_ids == {test_task_a.id}
        assert any(t["id"] == test_tracker_a.id for t in trackers)
        assert all(t["id"] != test_tracker_b.id for t in trackers)

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_explicit_unauthorized_task_id_returns_empty(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_tracker_b,
        test_task_a,
        test_task_b,
    ):
        # Caller is authorized for task A only, but explicitly filters on task B.
        # The explicit filter is honored only within the authorized set, so the
        # result is empty -- not a 404.
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(search_items=[test_task_a.id]),
        ):
            response = await isolated_client.get(f"/tracker?task_id={test_task_b.id}")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_explicit_authorized_task_id_returns_trackers(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_tracker_b,
        test_task_a,
        test_task_b,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(search_items=[test_task_a.id]),
        ):
            response = await isolated_client.get(f"/tracker?task_id={test_task_a.id}")
        assert response.status_code == 200
        trackers = response.json()
        assert {t["task_id"] for t in trackers} == {test_task_a.id}
        assert any(t["id"] == test_tracker_a.id for t in trackers)

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=False,
    )
    async def test_list_authz_disabled_returns_all(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_tracker_b,
        test_task_a,
        test_task_b,
    ):
        # With authz disabled the search is bypassed (authorized_task_ids is
        # None), so the full unfiltered set comes back -- including task B's
        # tracker that the filtered path would drop.
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(),
        ):
            response = await isolated_client.get("/tracker")
        assert response.status_code == 200
        returned_task_ids = {t["task_id"] for t in response.json()}
        assert {test_task_a.id, test_task_b.id} <= returned_task_ids

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_zero_authorized_no_filter_returns_empty(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_tracker_b,
    ):
        # Authorized for zero tasks and no explicit task_id: the empty-search
        # path must yield an empty list, not the full set.
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(search_items=[]),
        ):
            response = await isolated_client.get("/tracker")
        assert response.status_code == 200
        assert response.json() == []

    # ── update ──

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
    async def test_update_tracker_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_task_a,
    ):
        response = await isolated_client.put(
            f"/tracker/{test_tracker_a.id}",
            json={"status": "COMPLETED"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"

        # Exactly one /v1/authz/check, on the parent task with the execute operation.
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task_a.id
        assert authz_data["operation"] == "execute"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_update_tracker_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_tracker_a,
        test_task_a,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task_a.id}),
        ):
            response = await isolated_client.put(
                f"/tracker/{test_tracker_a.id}",
                json={"status": "COMPLETED"},
            )
        # Denial on the parent task must collapse to 404, not surface as 403.
        assert response.status_code == 404
