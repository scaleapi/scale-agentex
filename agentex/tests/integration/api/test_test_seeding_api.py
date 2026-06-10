"""Integration tests for the test-only /test/seed endpoint.

Covers:
  - Gate behavior (flag off, prod env, missing/wrong token) -> 404
  - Happy path: event row is persisted and returned
  - Audit marker injected into content
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.api.app import fastapi_app
from src.api.routes import test_seeding as test_seeding_route
from src.api.routes.test_seeding import get_seeding_env_vars
from src.config.environment_variables import Environment
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.use_cases.test_seeding_use_case import TestSeedingUseCase
from src.utils.ids import orm_id

VALID_TOKEN = "test-seed-token-abc123"


class _FakeEnvVars:
    """Minimal stand-in for EnvironmentVariables; only the attrs the gate reads."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        environment: str = Environment.DEV,
        token: str | None = VALID_TOKEN,
    ) -> None:
        self.ENABLE_TEST_SEEDING = enabled
        self.ENVIRONMENT = environment
        self.TEST_SEED_TOKEN = token


@pytest_asyncio.fixture
async def seeded_agent_and_task(isolated_repositories):
    """Create an agent + task so seeded events have valid FKs."""
    agent = await isolated_repositories["agent_repository"].create(
        AgentEntity(
            id=orm_id(),
            name="seed-test-agent",
            description="seed",
            acp_url="http://acp:8000",
            acp_type=ACPType.SYNC,
        )
    )
    task = await isolated_repositories["task_repository"].create(
        agent_id=agent.id,
        task=TaskEntity(
            id=orm_id(),
            name="seed-test-task",
            status=TaskStatus.RUNNING,
            status_reason="seed",
        ),
    )
    return {"agent": agent, "task": task}


@pytest_asyncio.fixture
async def seeding_client(isolated_integration_app, isolated_repositories):
    """Provide an httpx client with the seeding router mounted + gate overridden.

    The seeding router is normally only mounted when ENABLE_TEST_SEEDING=true at
    process start. In tests we register the router on fastapi_app manually and
    override DEnvironmentVariables to control the gate per test.
    """
    # Mount the router (idempotent - FastAPI tolerates re-includes only via
    # checking existing routes; safer to add once and rely on dependency
    # overrides for gate behavior).
    already_mounted = any(
        getattr(r, "path", None) == "/test/seed" for r in fastapi_app.routes
    )
    if not already_mounted:
        fastapi_app.include_router(test_seeding_route.router)

    # Wire the use case to the isolated event repository.
    def _make_use_case():
        return TestSeedingUseCase(
            event_repository=isolated_repositories["event_repository"]
        )

    fastapi_app.dependency_overrides[TestSeedingUseCase] = _make_use_case

    # Default to enabled + dev env + valid token.
    fastapi_app.dependency_overrides[get_seeding_env_vars] = lambda: _FakeEnvVars()

    from src.api.app import app as wrapped_app

    async with AsyncClient(
        transport=ASGITransport(app=wrapped_app), base_url="http://test"
    ) as client:
        yield client, isolated_repositories


def _override_env(env_vars: _FakeEnvVars) -> None:
    fastapi_app.dependency_overrides[get_seeding_env_vars] = lambda: env_vars


@pytest.mark.integration
class TestTestSeedingGate:
    @pytest.mark.asyncio
    async def test_flag_off_returns_404(self, seeding_client, seeded_agent_and_task):
        client, _ = seeding_client
        _override_env(_FakeEnvVars(enabled=False))
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                },
            },
            headers={"X-Test-Seed-Token": VALID_TOKEN},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_prod_env_returns_404_even_with_flag_on(
        self, seeding_client, seeded_agent_and_task
    ):
        client, _ = seeding_client
        _override_env(_FakeEnvVars(enabled=True, environment=Environment.PROD))
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                },
            },
            headers={"X-Test-Seed-Token": VALID_TOKEN},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_token_returns_404(
        self, seeding_client, seeded_agent_and_task
    ):
        client, _ = seeding_client
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                },
            },
            headers={"X-Test-Seed-Token": "wrong-token"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_token_returns_404(
        self, seeding_client, seeded_agent_and_task
    ):
        client, _ = seeding_client
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                },
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_token_not_configured_returns_404(
        self, seeding_client, seeded_agent_and_task
    ):
        client, _ = seeding_client
        _override_env(_FakeEnvVars(enabled=True, token=None))
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                },
            },
            headers={"X-Test-Seed-Token": "anything"},
        )
        assert resp.status_code == 404


@pytest.mark.integration
class TestTestSeedingEvent:
    @pytest.mark.asyncio
    async def test_seed_event_happy_path(
        self, seeding_client, seeded_agent_and_task
    ):
        client, repos = seeding_client
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                    "content": {"hello": "world"},
                },
            },
            headers={"X-Test-Seed-Token": VALID_TOKEN},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["task_id"] == seeded_agent_and_task["task"].id
        assert body["agent_id"] == seeded_agent_and_task["agent"].id
        assert body["id"]
        assert isinstance(body["sequence_id"], int)

        # Verify the row is in the repo
        listed = await repos["event_repository"].list_events_after_last_processed(
            task_id=seeded_agent_and_task["task"].id,
            agent_id=seeded_agent_and_task["agent"].id,
        )
        assert len(listed) == 1
        assert listed[0].id == body["id"]

    @pytest.mark.asyncio
    async def test_seed_event_audit_marker_present(
        self, seeding_client, seeded_agent_and_task
    ):
        client, repos = seeding_client
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                    "content": {"foo": "bar"},
                },
            },
            headers={"X-Test-Seed-Token": VALID_TOKEN},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        # Response uses TaskMessageContent (api schema). The DataContentEntity
        # round-trips through the API as {"type": "data", "data": {...}}.
        content = body["content"]
        assert content is not None
        assert content["type"] == "data"
        data = content["data"]
        assert data.get("seeded") is True
        assert "seeded_at" in data and isinstance(data["seeded_at"], str)
        # Caller-provided keys preserved alongside the marker.
        assert data.get("foo") == "bar"

    @pytest.mark.asyncio
    async def test_seed_event_audit_marker_when_no_content(
        self, seeding_client, seeded_agent_and_task
    ):
        client, _ = seeding_client
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                },
            },
            headers={"X-Test-Seed-Token": VALID_TOKEN},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["content"]["data"]
        assert data == {"seeded": True, "seeded_at": data["seeded_at"]}

    @pytest.mark.asyncio
    async def test_seed_event_id_override(
        self, seeding_client, seeded_agent_and_task
    ):
        client, _ = seeding_client
        override_id = orm_id()
        resp = await client.post(
            "/test/seed",
            json={
                "resource_type": "event",
                "payload": {
                    "task_id": seeded_agent_and_task["task"].id,
                    "agent_id": seeded_agent_and_task["agent"].id,
                    "id": override_id,
                },
            },
            headers={"X-Test-Seed-Token": VALID_TOKEN},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["id"] == override_id
