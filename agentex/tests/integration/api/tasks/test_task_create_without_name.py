"""
Integration test confirming a task can be created without a name.

``tasks.name`` is nullable, so the name is optional: a name-less task is accepted
and, because NULLs are exempt from the unique constraint, every name-less create
produces a brand-new task (no get-or-create-by-name dedup kicks in).
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestTaskCreateWithoutName:
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
            )
        )

    async def test_can_create_task_without_name(self, isolated_repositories, agent):
        task_repo = isolated_repositories["task_repository"]

        first = await task_repo.create(
            agent_id=agent.id,
            task=TaskEntity(id=orm_id(), name=None, status=TaskStatus.RUNNING),
        )
        second = await task_repo.create(
            agent_id=agent.id,
            task=TaskEntity(id=orm_id(), name=None, status=TaskStatus.RUNNING),
        )

        assert first.name is None
        assert second.name is None
        assert first.id != second.id
