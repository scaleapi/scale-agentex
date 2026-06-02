"""
Integration test confirming a task can be created without a name, using the same
shape an orchestrator (e.g. BP) sends.

BP issues a ``task/create`` RPC like:

    client.agents.rpc_by_name(
        agent_name=...,
        method="task/create",
        params={"name": display_name, "params": {...}},
    )

This test feeds that same ``params`` dict -- but with the ``name`` key omitted --
into the real ``task/create`` handler (``AgentsACPUseCase._handle_task_create``)
against real Postgres/Mongo/Redis. It confirms:

- the CreateTaskRequest schema accepts a params dict with no ``name`` (name is optional), and
- each name-less create yields a brand-new task (no get-or-create-by-name dedup).

A SYNC agent is used so ``task/create`` does not forward to a live ACP process;
the name handling is identical for ASYNC agents.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from src.api.schemas.agents_rpc import CreateTaskRequest
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.services.task_message_service import TaskMessageService
from src.domain.services.task_service import AgentTaskService
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestTaskCreateWithoutName:
    @pytest_asyncio.fixture
    async def acp_use_case(self, isolated_repositories):
        acp_client = AsyncMock()
        task_service = AgentTaskService(
            acp_client=acp_client,
            task_repository=isolated_repositories["task_repository"],
            task_state_repository=isolated_repositories["task_state_repository"],
            event_repository=isolated_repositories["event_repository"],
            stream_repository=isolated_repositories["redis_stream_repository"],
        )
        authorization_service = AsyncMock()
        authorization_service.grant = AsyncMock(return_value=None)
        return AgentsACPUseCase(
            agent_repository=isolated_repositories["agent_repository"],
            deployment_repository=isolated_repositories["deployment_repository"],
            acp_client=acp_client,
            task_service=task_service,
            task_message_service=TaskMessageService(
                message_repository=isolated_repositories["task_message_repository"],
            ),
            authorization_service=authorization_service,
        )

    @pytest_asyncio.fixture
    async def agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        return await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="no-name-test-agent",
                description="Agent for name-optional task test",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
                status=AgentStatus.READY,
            )
        )

    async def test_task_create_without_name(self, acp_use_case, agent):
        # BP-shaped task/create params, with the `name` key omitted entirely.
        params_without_name = {"params": {"prompt": "do the thing"}}

        # The schema accepts it (name is optional) -- this is the assertion that
        # mirrors "can BP call task/create without a name?".
        request = CreateTaskRequest(**params_without_name)
        assert request.name is None

        first = await acp_use_case._handle_task_create(
            agent=agent, params=request, acp_url=agent.acp_url
        )
        second = await acp_use_case._handle_task_create(
            agent=agent,
            params=CreateTaskRequest(**{"params": {"prompt": "do another thing"}}),
            acp_url=agent.acp_url,
        )

        assert first.name is None
        assert second.name is None
        # No name -> no dedup -> a brand-new task each time.
        assert first.id != second.id
