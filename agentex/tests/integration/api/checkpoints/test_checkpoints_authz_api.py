"""
Integration tests for checkpoint-route authorization.

Checkpoint routes have no authorization type of their own. Each route enforces
on the owning task (``thread_id`` is the task id) via ``DAuthorizedBodyId(task, ...)``:

* get-tuple / list -> ``task.read`` (view).
* put / put-writes -> ``task.update`` (editor + owner); delete-thread -> ``task.delete``.

Per the canonical ``DAuthorizedBodyId`` task wrap, a denied check on the parent
task collapses to 404 (not 403) on every route — reads and writes alike — so
callers cannot probe cross-tenant existence by comparing response codes.
"""

from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from src.adapters.authorization.exceptions import AuthorizationError
from src.api.schemas.authorization_types import AgentexResourceType
from src.domain.entities.agents import ACPType, AgentEntity
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
class TestCheckpointsAuthzAPIIntegration:
    """End-to-end integration tests for checkpoint-route authorization."""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        agent = AgentEntity(
            id=orm_id(),
            name="test-authz-agent",
            description="Agent for checkpoint-authz tests",
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
            status_reason="Task for checkpoint-authz tests",
        )
        return await task_repo.create(agent_id=test_agent.id, task=task)

    @pytest_asyncio.fixture
    async def test_checkpoint(self, isolated_repositories, test_task):
        """Persist one checkpoint whose thread_id is the parent task id."""
        checkpoint_repo = isolated_repositories["checkpoint_repository"]
        await checkpoint_repo.put(
            thread_id=test_task.id,
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1", "v": 4},
            metadata={"source": "input", "step": 1},
            blobs=[],
        )
        return test_task.id

    # ── get-tuple ──

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
    async def test_get_tuple_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_checkpoint,
        test_task,
    ):
        response = await isolated_client.post(
            "/checkpoints/get-tuple", json={"thread_id": test_task.id}
        )
        assert response.status_code == 200
        assert response.json()["checkpoint_id"] == "cp-1"

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
    async def test_get_tuple_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_checkpoint,
        test_task,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task.id}),
        ):
            response = await isolated_client.post(
                "/checkpoints/get-tuple", json={"thread_id": test_task.id}
            )
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
    @patch(
        "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
        side_effect=_mock_post_factory(),
    )
    async def test_list_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_checkpoint,
        test_task,
    ):
        response = await isolated_client.post(
            "/checkpoints/list", json={"thread_id": test_task.id}
        )
        assert response.status_code == 200
        body = response.json()
        assert any(item["checkpoint_id"] == "cp-1" for item in body)

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

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_list_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_checkpoint,
        test_task,
    ):
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task.id}),
        ):
            response = await isolated_client.post(
                "/checkpoints/list", json={"thread_id": test_task.id}
            )
        # Denial on the parent task must collapse to 404, not surface as 403.
        assert response.status_code == 404

    # ── put ──

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
    async def test_put_authorized_returns_200(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_task,
    ):
        response = await isolated_client.post(
            "/checkpoints/put",
            json={
                "thread_id": test_task.id,
                "checkpoint_ns": "",
                "checkpoint_id": "cp-1",
                "checkpoint": {"id": "cp-1", "v": 4},
                "metadata": {"step": 1},
                "blobs": [],
            },
        )
        assert response.status_code == 200
        assert response.json()["checkpoint_id"] == "cp-1"

        # Writes check the parent task with the update operation
        # (task.update = editor + owner), so editors can write without owner.
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task.id
        assert authz_data["operation"] == "update"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_put_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_task,
    ):
        # A denied write on the parent task collapses to 404 (not 403) via the
        # canonical task body-id wrap — the same as for the read routes.
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task.id}),
        ):
            response = await isolated_client.post(
                "/checkpoints/put",
                json={
                    "thread_id": test_task.id,
                    "checkpoint_ns": "",
                    "checkpoint_id": "cp-1",
                    "checkpoint": {"id": "cp-1", "v": 4},
                    "metadata": {"step": 1},
                    "blobs": [],
                },
            )
        assert response.status_code == 404

    # ── put-writes ──

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
    async def test_put_writes_authorized_returns_204(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_task,
    ):
        response = await isolated_client.post(
            "/checkpoints/put-writes",
            json={
                "thread_id": test_task.id,
                "checkpoint_ns": "",
                "checkpoint_id": "cp-1",
                "writes": [
                    {
                        "task_id": "lg-task-1",
                        "idx": 0,
                        "channel": "messages",
                        "type": "json",
                        "blob": "eyJyb2xlIjogImFpIn0=",
                        "task_path": "",
                    }
                ],
                "upsert": False,
            },
        )
        assert response.status_code == 204

        # Like put, put-writes checks the parent task with the update operation.
        check_calls = [
            call
            for call in post_with_error_handling_mock.call_args_list
            if call[0][1] == "/v1/authz/check"
        ]
        assert len(check_calls) == 1
        authz_data = check_calls[0][1]["json"]
        assert authz_data["resource"]["type"] == AgentexResourceType.task.value
        assert authz_data["resource"]["selector"] == test_task.id
        assert authz_data["operation"] == "update"

    @pytest.mark.asyncio
    @patch(
        "src.api.authentication_middleware.AgentexAuthMiddleware.is_enabled",
        return_value=True,
    )
    @patch(
        "src.domain.services.authorization_service.AuthorizationService.is_enabled",
        return_value=True,
    )
    async def test_put_writes_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_task,
    ):
        # A denied write on the parent task collapses to 404 (not 403).
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task.id}),
        ):
            response = await isolated_client.post(
                "/checkpoints/put-writes",
                json={
                    "thread_id": test_task.id,
                    "checkpoint_ns": "",
                    "checkpoint_id": "cp-1",
                    "writes": [
                        {
                            "task_id": "lg-task-1",
                            "idx": 0,
                            "channel": "messages",
                            "type": "json",
                            "blob": "eyJyb2xlIjogImFpIn0=",
                            "task_path": "",
                        }
                    ],
                    "upsert": False,
                },
            )
        assert response.status_code == 404

    # ── delete-thread ──

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
    async def test_delete_thread_authorized_returns_204(
        self,
        post_with_error_handling_mock,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_checkpoint,
        test_task,
    ):
        response = await isolated_client.post(
            "/checkpoints/delete-thread", json={"thread_id": test_task.id}
        )
        assert response.status_code == 204

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
    async def test_delete_thread_unauthorized_returns_404(
        self,
        is_enabled_authorization_mock,
        is_enabled_mock,
        isolated_client,
        test_checkpoint,
        test_task,
    ):
        # delete-thread maps to task.delete (owner-only, the most restrictive
        # permission). A denied check must collapse to 404 (not 403) so the
        # route preserves the cross-tenant opacity guarantee.
        with patch(
            "src.utils.http_request_handler.HttpRequestHandler.post_with_error_handling",
            side_effect=_mock_post_factory(deny_task_ids={test_task.id}),
        ):
            response = await isolated_client.post(
                "/checkpoints/delete-thread", json={"thread_id": test_task.id}
            )
        assert response.status_code == 404
