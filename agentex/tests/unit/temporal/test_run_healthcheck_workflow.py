from types import SimpleNamespace

import pytest
from src.domain.entities.agents import AgentStatus
from src.temporal import run_healthcheck_workflow
from temporalio.common import WorkflowIDReusePolicy


async def _run_main_with_pages(monkeypatch, pages):
    class FakeGlobalDependencies:
        temporal_client = object()

        async def load(self):
            return None

    class FakeAgentRepository:
        async def list(
            self,
            filters,
            limit,
            page_number,
            order_by,
            order_direction,
        ):
            call = {
                "filters": filters,
                "limit": limit,
                "page_number": page_number,
                "order_by": order_by,
                "order_direction": order_direction,
            }
            self.calls.append(call)
            return pages.get((filters["status"], page_number), [])

        def __init__(self, *args):
            self.calls = []

    class FakeTemporalAdapter:
        def __init__(self, temporal_client):
            self.temporal_client = temporal_client
            self.started_workflows = []
            self.created_schedules = []

        async def start_workflow(self, **kwargs):
            self.started_workflows.append(kwargs)

        async def create_schedule(self, **kwargs):
            self.created_schedules.append(kwargs)

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


def _agents(count: int, status: AgentStatus, prefix: str = "agent"):
    return [
        SimpleNamespace(
            id=f"{prefix}-{i}",
            acp_url=f"http://{prefix}-{i}",
            status=status,
        )
        for i in range(count)
    ]


def _expected_call(status: AgentStatus, page_number: int):
    return {
        "filters": {"status": status},
        "limit": run_healthcheck_workflow.MONITORED_AGENT_PAGE_SIZE,
        "page_number": page_number,
        "order_by": "id",
        "order_direction": "asc",
    }


@pytest.mark.asyncio
@pytest.mark.unit
async def test_main_reconciles_ready_and_unhealthy_agents(monkeypatch):
    ready = _agents(1, AgentStatus.READY, "ready")[0]
    unhealthy = _agents(1, AgentStatus.UNHEALTHY, "unhealthy")[0]

    fake_repo, fake_adapter = await _run_main_with_pages(
        monkeypatch,
        {
            (AgentStatus.READY, 1): [ready],
            (AgentStatus.UNHEALTHY, 1): [unhealthy],
        },
    )

    assert fake_repo.calls == [
        _expected_call(AgentStatus.READY, 1),
        _expected_call(AgentStatus.UNHEALTHY, 1),
    ]
    assert [
        call["args"][0]["initial_status"] for call in fake_adapter.started_workflows
    ] == ["Ready", "Unhealthy"]
    for call in fake_adapter.started_workflows:
        assert call["id_reuse_policy"] == WorkflowIDReusePolicy.ALLOW_DUPLICATE
    assert fake_adapter.created_schedules[0]["interval_seconds"] == 300
    assert fake_adapter.created_schedules[0]["overlap_policy"] == "skip"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_main_pages_each_monitored_status(monkeypatch):
    page_size = run_healthcheck_workflow.MONITORED_AGENT_PAGE_SIZE
    pages = {
        (AgentStatus.READY, 1): _agents(page_size, AgentStatus.READY, "ready"),
        (AgentStatus.READY, 2): _agents(1, AgentStatus.READY, "ready-final"),
        (AgentStatus.UNHEALTHY, 1): _agents(
            page_size, AgentStatus.UNHEALTHY, "unhealthy"
        ),
        (AgentStatus.UNHEALTHY, 2): _agents(
            1, AgentStatus.UNHEALTHY, "unhealthy-final"
        ),
    }

    fake_repo, fake_adapter = await _run_main_with_pages(monkeypatch, pages)

    assert fake_repo.calls == [
        _expected_call(AgentStatus.READY, 1),
        _expected_call(AgentStatus.READY, 2),
        _expected_call(AgentStatus.UNHEALTHY, 1),
        _expected_call(AgentStatus.UNHEALTHY, 2),
    ]
    assert len(fake_adapter.started_workflows) == (2 * page_size) + 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_main_skips_agent_without_acp_url(monkeypatch):
    agent = SimpleNamespace(
        id="agent-without-url",
        acp_url=None,
        status=AgentStatus.UNHEALTHY,
    )

    _, fake_adapter = await _run_main_with_pages(
        monkeypatch,
        {(AgentStatus.UNHEALTHY, 1): [agent]},
    )

    assert fake_adapter.started_workflows == []
