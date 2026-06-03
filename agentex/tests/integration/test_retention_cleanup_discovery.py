from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert
from src.adapters.orm import AgentORM, TaskAgentORM, TaskORM
from src.domain.entities.agents import AgentStatus
from src.domain.entities.tasks import TaskStatus


async def _seed_agent(session, agent_id: str, name: str) -> None:
    await session.execute(
        insert(AgentORM).values(
            id=agent_id,
            name=name,
            description="seed",
            acp_url=f"http://{agent_id}:8000",
            acp_type="sync",
            status=AgentStatus.READY,
        )
    )


async def _seed_task(
    session,
    *,
    task_id: str,
    agent_id: str,
    updated_at: datetime,
    cleaned_at: datetime | None,
    status: TaskStatus = TaskStatus.COMPLETED,
) -> None:
    await session.execute(
        insert(TaskORM).values(
            id=task_id,
            name=task_id,
            status=status,
            updated_at=updated_at,
            cleaned_at=cleaned_at,
        )
    )
    await session.execute(
        insert(TaskAgentORM).values(task_id=task_id, agent_id=agent_id)
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_filters_and_keyset_paging(isolated_repositories):
    repo = isolated_repositories["task_repository"]
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    async with isolated_repositories["postgres_rw_session_factory"]() as session:
        await _seed_agent(session, "agent-allowed", "allowed-agent")
        await _seed_agent(session, "agent-other", "other-agent")
        await _seed_task(
            session,
            task_id="t-aaa",
            agent_id="agent-allowed",
            updated_at=old,
            cleaned_at=None,
        )
        await _seed_task(
            session,
            task_id="t-bbb",
            agent_id="agent-allowed",
            updated_at=old,
            cleaned_at=None,
        )
        await _seed_task(
            session,
            task_id="t-fresh",
            agent_id="agent-allowed",
            updated_at=now,
            cleaned_at=None,
        )
        await _seed_task(
            session,
            task_id="t-clean",
            agent_id="agent-allowed",
            updated_at=old,
            cleaned_at=old,
        )
        await _seed_task(
            session,
            task_id="t-other",
            agent_id="agent-other",
            updated_at=old,
            cleaned_at=None,
        )
        await session.commit()

    ids = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=["allowed-agent"], after_id=None, limit=100
    )
    assert ids == ["t-aaa", "t-bbb"]

    page1 = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=["allowed-agent"], after_id=None, limit=1
    )
    assert page1 == ["t-aaa"]
    page2 = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=["allowed-agent"], after_id="t-aaa", limit=1
    )
    assert page2 == ["t-bbb"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_empty_allowlist_returns_nothing(isolated_repositories):
    repo = isolated_repositories["task_repository"]
    ids = await repo.list_cleanup_candidate_ids(
        idle_days=7, agent_names=[], after_id=None, limit=100
    )
    assert ids == []
