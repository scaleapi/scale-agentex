from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import src.temporal.activities.scheduled_agent_run_activities as activities_module
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.routes.agent_run_schedules import _extract_creator_principal
from src.domain.entities.agent_run_schedules import AgentRunScheduleEntity
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.agents_rpc import AgentRPCMethod
from src.domain.entities.task_messages import MessageAuthor, TextContentEntity
from src.domain.entities.tasks import TaskEntity
from src.temporal.activities.scheduled_agent_run_activities import (
    ScheduledAgentRunActivities,
    _build_initial_content,
)


def _agent(acp_type=ACPType.ASYNC, status=AgentStatus.READY):
    return AgentEntity(
        id="agent-1",
        name="test-agent",
        description="A test agent",
        status=status,
        acp_type=acp_type,
        acp_url="http://acp.example.com",
    )


def _schedule(**overrides) -> AgentRunScheduleEntity:
    payload: dict = {
        "id": str(uuid4()),
        "agent_id": "agent-1",
        "name": "daily-summary",
        "cron_expression": "0 17 * * *",
        "creator_principal": {"user_id": "u1", "account_id": "a1"},
        "initial_input": {"type": "text", "author": "user", "content": "hello"},
    }
    payload.update(overrides)
    return AgentRunScheduleEntity(**payload)


def _fake_use_case(agent, created_task):
    use_case = MagicMock()
    use_case.agent_repository = AsyncMock()
    use_case.agent_repository.get.return_value = agent
    use_case.handle_rpc_request = AsyncMock(return_value=created_task)
    use_case.task_service = AsyncMock()
    # AuthZ check succeeds by default (no-op / allowed).
    use_case.authorization_service = AsyncMock()
    use_case.authorization_service.check = AsyncMock(return_value=True)
    return use_case


@pytest.fixture
def activity_instance(monkeypatch):
    instance = ScheduledAgentRunActivities(
        global_dependencies=MagicMock(),
        schedule_repository=AsyncMock(),
    )
    return instance


def _patch_use_case(monkeypatch, use_case):
    monkeypatch.setattr(
        activities_module,
        "build_acp_use_case_for_principal",
        lambda *args, **kwargs: use_case,
    )


class TestBuildInitialContent:
    def test_builds_text_content(self):
        content = _build_initial_content(
            {"type": "text", "author": "user", "content": "hi there"}
        )
        assert isinstance(content, TextContentEntity)
        assert content.content == "hi there"
        assert content.author == MessageAuthor.USER


class TestExtractCreatorPrincipal:
    def test_strips_to_safe_subset(self):
        principal = {
            "user_id": "u1",
            "account_id": "a1",
            "principal_type": "user",
            # credentials that must never be persisted:
            "cookie": "session=abc",
            "api_key": "sk-123",
            "authorization": "Bearer xyz",
        }
        result = _extract_creator_principal(principal)
        assert result == {
            "user_id": "u1",
            "account_id": "a1",
            "principal_type": "user",
        }
        assert "cookie" not in result
        assert "api_key" not in result
        assert "authorization" not in result

    def test_none_principal_yields_empty(self):
        assert _extract_creator_principal(None) == {}


@pytest.mark.unit
@pytest.mark.asyncio
class TestLaunchScheduledAgentRun:
    async def test_skips_when_schedule_missing(self, activity_instance):
        activity_instance.schedule_repository.get.side_effect = ItemDoesNotExist("x")

        result = await activity_instance.launch_scheduled_agent_run("sched-1", "fire-1")

        assert result["status"] == "skipped"
        assert result["reason"] == "schedule_not_found"

    async def test_skips_when_paused(self, activity_instance):
        activity_instance.schedule_repository.get.return_value = _schedule(paused=True)

        result = await activity_instance.launch_scheduled_agent_run("sched-1", "fire-1")

        assert result["status"] == "skipped"
        assert result["reason"] == "schedule_paused"

    async def test_async_agent_delivers_via_event_send(
        self, activity_instance, monkeypatch
    ):
        schedule = _schedule()
        activity_instance.schedule_repository.get.return_value = schedule
        task = TaskEntity(id="task-1", task_metadata={"schedule_id": schedule.id})
        use_case = _fake_use_case(_agent(ACPType.ASYNC), task)
        _patch_use_case(monkeypatch, use_case)

        result = await activity_instance.launch_scheduled_agent_run(
            schedule.id, "fire-1"
        )

        assert result["status"] == "launched"
        assert result["method"] == "event/send"
        methods = [
            call.kwargs["method"] for call in use_case.handle_rpc_request.call_args_list
        ]
        assert methods == [AgentRPCMethod.TASK_CREATE, AgentRPCMethod.EVENT_SEND]
        # Deterministic task name embeds schedule id + fire id.
        create_params = use_case.handle_rpc_request.call_args_list[0].kwargs["params"]
        assert create_params.name == f"scheduled-run:{schedule.id}:fire-1"
        use_case.task_service.update_task.assert_awaited_once()
        # Fire-time authz mirrors the RPC route: agent.execute, then task.create,
        # then task.update on the created task — in that order.
        from src.api.schemas.authorization_types import (
            AgentexResourceType,
            AuthorizedOperationType,
        )

        checks = [
            (c.kwargs["resource"].type, c.kwargs["operation"])
            for c in use_case.authorization_service.check.call_args_list
        ]
        assert checks == [
            (AgentexResourceType.agent, AuthorizedOperationType.execute),
            (AgentexResourceType.task, AuthorizedOperationType.create),
            (AgentexResourceType.task, AuthorizedOperationType.update),
        ]

    async def test_sync_agent_delivers_via_message_send(
        self, activity_instance, monkeypatch
    ):
        schedule = _schedule()
        activity_instance.schedule_repository.get.return_value = schedule
        task = TaskEntity(id="task-1")
        use_case = _fake_use_case(_agent(ACPType.SYNC), task)
        _patch_use_case(monkeypatch, use_case)

        result = await activity_instance.launch_scheduled_agent_run(
            schedule.id, "fire-1"
        )

        assert result["method"] == "message/send"
        methods = [
            call.kwargs["method"] for call in use_case.handle_rpc_request.call_args_list
        ]
        assert methods == [AgentRPCMethod.TASK_CREATE, AgentRPCMethod.MESSAGE_SEND]

    async def test_skips_delivery_when_already_delivered(
        self, activity_instance, monkeypatch
    ):
        schedule = _schedule()
        activity_instance.schedule_repository.get.return_value = schedule
        # Retry case: the deterministic task already carries the delivered marker.
        task = TaskEntity(
            id="task-1", task_metadata={"scheduled_input_delivered": True}
        )
        use_case = _fake_use_case(_agent(ACPType.ASYNC), task)
        _patch_use_case(monkeypatch, use_case)

        result = await activity_instance.launch_scheduled_agent_run(
            schedule.id, "fire-1"
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "input_already_delivered"
        # Only task/create ran; no second delivery call.
        assert use_case.handle_rpc_request.call_count == 1
        use_case.task_service.update_task.assert_not_awaited()

    async def test_skips_when_creator_permission_revoked(
        self, activity_instance, monkeypatch
    ):
        from src.adapters.authorization.exceptions import AuthorizationError

        schedule = _schedule()
        activity_instance.schedule_repository.get.return_value = schedule
        use_case = _fake_use_case(_agent(ACPType.ASYNC), TaskEntity(id="t"))
        # Creator's create permission was revoked since the schedule was made.
        use_case.authorization_service.check = AsyncMock(
            side_effect=AuthorizationError(message="forbidden")
        )
        _patch_use_case(monkeypatch, use_case)

        result = await activity_instance.launch_scheduled_agent_run(
            schedule.id, "fire-1"
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "permission_denied"
        # Denied before any task creation.
        use_case.handle_rpc_request.assert_not_called()

    async def test_skips_when_agent_deleted(self, activity_instance, monkeypatch):
        schedule = _schedule()
        activity_instance.schedule_repository.get.return_value = schedule
        use_case = _fake_use_case(
            _agent(ACPType.ASYNC, status=AgentStatus.DELETED), TaskEntity(id="t")
        )
        _patch_use_case(monkeypatch, use_case)

        result = await activity_instance.launch_scheduled_agent_run(
            schedule.id, "fire-1"
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "agent_deleted"
