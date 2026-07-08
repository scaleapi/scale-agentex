from types import SimpleNamespace

import pytest
from src.temporal import run_healthcheck_workflow


async def _run_main_with_pages(monkeypatch, pages):
    class FakeGlobalDependencies:
        temporal_client = object()

        async def load(self):
            return None

    class FakeAgentRepository:
        def __init__(self, *args):
            self.calls = []

        async def list(
            self,
            filters,
            limit,
            page_number,
            order_by,
            order_direction,
        ):
            self.calls.append(
                {
                    "filters": filters,
                    "limit": limit,
                    "page_number": page_number,
                    "order_by": order_by,
                    "order_direction": order_direction,
                }
            )
            return pages.get(page_number, [])

    class FakeTemporalAdapter:
        def __init__(self, temporal_client):
            self.temporal_client = temporal_client
            self.started_workflows = []

        async def start_workflow(self, **kwargs):
            self.started_workflows.append(kwargs)

    fake_repo = FakeAgentRepository()
    fake_adapter = FakeTemporalAdapter(object())
    fake_env = SimpleNamespace(
        ENABLE_HEALTH_CHECK_WORKFLOW=True,
        AGENTEX_SERVER_TASK_QUEUE="agentex-server",
    )

    monkeypatch.setattr(
        run_healthcheck_workflow,
        "GlobalDependencies",
        FakeGlobalDependencies,
    )
    monkeypatch.setattr(
        run_healthcheck_workflow.EnvironmentVariables,
        "refresh",
        lambda: fake_env,
    )
    monkeypatch.setattr(
        run_healthcheck_workflow.TemporalClientFactory,
        "is_temporal_configured",
        lambda env: True,
    )
    monkeypatch.setattr(
        run_healthcheck_workflow,
        "database_async_read_write_engine",
        lambda: object(),
    )
    monkeypatch.setattr(
        run_healthcheck_workflow,
        "database_async_read_write_session_maker",
        lambda engine: object(),
    )
    monkeypatch.setattr(
        run_healthcheck_workflow,
        "database_async_read_only_session_maker",
        lambda engine: object(),
    )
    monkeypatch.setattr(
        run_healthcheck_workflow,
        "AgentRepository",
        lambda *args: fake_repo,
    )
    monkeypatch.setattr(
        run_healthcheck_workflow,
        "TemporalAdapter",
        lambda temporal_client: fake_adapter,
    )

    await run_healthcheck_workflow.main()

    return fake_repo, fake_adapter


def _agents(count: int, prefix: str = "agent"):
    return [
        SimpleNamespace(id=f"{prefix}-{i}", acp_url=f"http://{prefix}-{i}")
        for i in range(count)
    ]


def _expected_call(page_number: int):
    return {
        "filters": {"status": run_healthcheck_workflow.AgentStatus.READY},
        "limit": run_healthcheck_workflow.READY_AGENT_PAGE_SIZE,
        "page_number": page_number,
        "order_by": "id",
        "order_direction": "asc",
    }


@pytest.mark.asyncio
@pytest.mark.unit
async def test_main_pages_ready_agents_for_healthcheck(monkeypatch):
    final_agent = SimpleNamespace(id="agent-final", acp_url="http://agent-final")
    fake_repo, fake_adapter = await _run_main_with_pages(
        monkeypatch,
        {
            1: _agents(run_healthcheck_workflow.READY_AGENT_PAGE_SIZE),
            2: [final_agent],
        },
    )

    assert fake_repo.calls == [_expected_call(1), _expected_call(2)]
    assert len(fake_adapter.started_workflows) == (
        run_healthcheck_workflow.READY_AGENT_PAGE_SIZE + 1
    )
    assert (
        fake_adapter.started_workflows[-1]["workflow_id"]
        == "healthcheck_workflow_agent-final"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_main_checks_empty_page_for_exact_page_size(monkeypatch):
    fake_repo, fake_adapter = await _run_main_with_pages(
        monkeypatch,
        {
            1: _agents(run_healthcheck_workflow.READY_AGENT_PAGE_SIZE),
            2: [],
        },
    )

    assert fake_repo.calls == [_expected_call(1), _expected_call(2)]
    assert len(fake_adapter.started_workflows) == (
        run_healthcheck_workflow.READY_AGENT_PAGE_SIZE
    )
