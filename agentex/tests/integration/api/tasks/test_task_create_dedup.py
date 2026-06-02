"""
Integration tests reproducing the task/create get-or-create-by-name behavior
the way a client actually triggers it.

This drives the *real* ``task/create`` code path -- ``AgentsACPUseCase._handle_task_create``
-> ``_get_or_create_task`` -- against real Postgres / MongoDB / Redis (testcontainers),
wiring the same services the API route uses. The only mocks are the outbound ACP
client (no real agent process to forward to) and the authorization service.

This mirrors how an orchestrator delegates to a sub-agent: it issues ``task/create``
with a task ``name`` derived from the prompt. When two delegations produce the same
name, the second ``task/create`` does NOT create a new task -- it silently returns
the first task, *including its prior message history*. That is the footgun:

    first  = task/create(name="summarize the q3 report")  -> task A (fresh)
    second = task/create(name="summarize the q3 report")  -> task A again (stale)

The companion ``test_task_name_uniqueness.py`` covers the database constraint that
makes this reuse possible; this file covers the user-facing behavior on top of it.

A SYNC agent is used so no outbound forward is attempted (forwarding only happens
for AGENTIC / ASYNC agents, and it happens *after* the get-or-create step on the
already-resolved task -- so the dedup behavior is identical regardless of ACP type).
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from src.api.schemas.agents_rpc import CreateTaskRequest
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.task_messages import (
    MessageAuthor,
    MessageStyle,
    TaskMessageContentType,
    TextContentEntity,
    TextFormat,
)
from src.domain.services.task_message_service import TaskMessageService
from src.domain.services.task_service import AgentTaskService
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestTaskCreateDedup:
    """Reproduce the task/create reuse-by-name behavior end-to-end through the use case."""

    @pytest_asyncio.fixture
    async def acp_use_case(self, isolated_repositories):
        """Wire the real AgentsACPUseCase with isolated repositories.

        Mirrors the dependency graph the API route builds; only the outbound ACP
        client and authorization service are mocked.
        """
        acp_client = AsyncMock()

        task_service = AgentTaskService(
            acp_client=acp_client,
            task_repository=isolated_repositories["task_repository"],
            task_state_repository=isolated_repositories["task_state_repository"],
            event_repository=isolated_repositories["event_repository"],
            stream_repository=isolated_repositories["redis_stream_repository"],
        )
        task_message_service = TaskMessageService(
            message_repository=isolated_repositories["task_message_repository"],
        )
        authorization_service = AsyncMock()
        authorization_service.grant = AsyncMock(return_value=None)

        return AgentsACPUseCase(
            agent_repository=isolated_repositories["agent_repository"],
            deployment_repository=isolated_repositories["deployment_repository"],
            acp_client=acp_client,
            task_service=task_service,
            task_message_service=task_message_service,
            authorization_service=authorization_service,
        )

    @pytest_asyncio.fixture
    async def agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        return await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="dedup-test-agent",
                description="Agent for task/create dedup tests",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
                status=AgentStatus.READY,
            )
        )

    async def test_same_name_returns_existing_task_with_stale_history(
        self, acp_use_case, agent, isolated_repositories
    ):
        """A second task/create with the same name returns the FIRST task, with its
        original params and message history intact -- not a fresh task."""
        task_name = "summarize the q3 report"

        # First delegation: creates a fresh task.
        first = await acp_use_case._handle_task_create(
            agent=agent,
            params=CreateTaskRequest(name=task_name, params={"attempt": "one"}),
            acp_url=agent.acp_url,
        )

        # Simulate the first run producing some conversation history.
        message_service = TaskMessageService(
            message_repository=isolated_repositories["task_message_repository"],
        )
        await message_service.append_message(
            task_id=first.id,
            content=TextContentEntity(
                type=TaskMessageContentType.TEXT,
                author=MessageAuthor.AGENT,
                style=MessageStyle.STATIC,
                format=TextFormat.PLAIN,
                content="output from the first delegation",
            ),
        )

        # Second delegation with the SAME name: expected to be a new task, but...
        second = await acp_use_case._handle_task_create(
            agent=agent,
            params=CreateTaskRequest(name=task_name, params={"attempt": "two"}),
            acp_url=agent.acp_url,
        )

        # ...it is the same task row, not a new one.
        assert second.id == first.id

        # Note the asymmetry in how the existing row is mutated on reuse:
        #   - params ARE updated in place to the second call's values, and
        #   - task_metadata is NOT (see the unit test
        #     test_handle_task_create_ignores_task_metadata_for_existing_task).
        # Either way it's the same underlying task/conversation, not a fresh one.
        assert second.params == {"attempt": "two"}

        # The stale conversation history from the first run is still attached -- this is
        # exactly what breaks a re-delegation that expected a clean task.
        messages = await message_service.get_messages(
            task_id=second.id, limit=50, page_number=1
        )
        assert len(messages) == 1
        assert messages[0].content.content == "output from the first delegation"

    async def test_omitting_name_creates_a_fresh_task_each_time(
        self, acp_use_case, agent
    ):
        """The workaround: omit the name and every task/create returns a brand-new task."""
        first = await acp_use_case._handle_task_create(
            agent=agent,
            params=CreateTaskRequest(name=None, params={"attempt": "one"}),
            acp_url=agent.acp_url,
        )
        second = await acp_use_case._handle_task_create(
            agent=agent,
            params=CreateTaskRequest(name=None, params={"attempt": "two"}),
            acp_url=agent.acp_url,
        )

        assert first.id != second.id
        assert first.name is None
        assert second.name is None
