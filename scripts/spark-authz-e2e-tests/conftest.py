"""Root conftest — session-scoped clients and function-scoped factories.

Fixtures:
  - config                  (session) — parsed config.json
  - authz_client            (session) — SparkAuthzClient for direct SpiceDB calls
  - agentex_client_a / _b   (session) — Agentex REST clients per user identity
  - user_a / user_b         (session) — IdentityCredentials
  - create_agent            (function) — creates an agent as user_a and registers cleanup
  - create_api_key          (function) — creates an api_key as user_a under a given agent
  - create_task             (function) — creates a task as user_a under a given agent
  - create_state            (function) — creates a state as user_a under a given task
  - cleanup                 (function) — cleanup tracker honoring config knobs

AGX1-325 scope: same-tenant user_a (owner) + user_b (no permission). No
cross-tenant or service identity here — those will be added if/when the
ticket grows to cover them.
"""

import json
import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from clients.agentex_client import AgentexClient, IdentityCredentials
from clients.spark_authz_client import SparkAuthzClient, SparkAuthzConfig
from helpers.cleanup import CleanupTracker
from helpers.factories import unique_agent_name, unique_api_key_name, unique_task_name

logger = logging.getLogger(__name__)

AGENT_RESOURCE_TYPE = "agent"
API_KEY_RESOURCE_TYPE = "api_key"
TASK_RESOURCE_TYPE = "task"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Attach phase reports to ``item`` so fixtures can read pass/fail in teardown."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        pytest.skip("config.json not found. Copy config.json.example and configure.")
    with open(config_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Identity credentials
# ---------------------------------------------------------------------------


def _make_credentials(config: dict, key: str) -> IdentityCredentials:
    u = config["users"][key]
    return IdentityCredentials(
        headers=u["headers"],
        identity_id=u["identity_id"],
        account_id=u["account_id"],
        subject_type=u.get("subject_type", "identity"),
    )


@pytest.fixture(scope="session")
def user_a(config) -> IdentityCredentials:
    return _make_credentials(config, "user_a")


@pytest.fixture(scope="session")
def user_b(config) -> IdentityCredentials:
    """Same-tenant user with no permission on user_a's resources by default."""
    if "user_b" not in (config.get("users") or {}):
        pytest.skip(
            "Add users.user_b to config.json (same account_id as user_a, distinct "
            "identity_id) to run negative-permission tests."
        )
    return _make_credentials(config, "user_b")


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def agentex_client_a(config, user_a) -> Generator[AgentexClient, None, None]:
    timeout = config.get("test_settings", {}).get("request_timeout_seconds", 30)
    client = AgentexClient(config["agentex_api"]["base_url"], user_a, timeout=timeout)
    yield client
    client.close()


@pytest.fixture(scope="session")
def agentex_client_b(config, user_b) -> Generator[AgentexClient, None, None]:
    timeout = config.get("test_settings", {}).get("request_timeout_seconds", 30)
    client = AgentexClient(config["agentex_api"]["base_url"], user_b, timeout=timeout)
    yield client
    client.close()


def _build_authz_client(config) -> SparkAuthzClient:
    authz_cfg = SparkAuthzConfig(
        host=config["spark_authz"]["host"],
        use_tls=config["spark_authz"].get("use_tls", False),
    )
    return SparkAuthzClient(authz_cfg)


def _spark_authz_reachable(config) -> bool:
    """Best-effort probe. Cached per-session via the calling fixture.

    Returns True only when /healthz returns a 2xx. ``httpx.get`` doesn't
    raise on non-2xx by default, so without the explicit status-code check
    a 503-Unavailable host would look healthy here; tests would then build
    the client and fail with a confusing ``HTTPStatusError`` on the first
    real call instead of skipping cleanly.
    """
    import httpx

    authz_cfg = SparkAuthzConfig(
        host=config["spark_authz"]["host"],
        use_tls=config["spark_authz"].get("use_tls", False),
    )
    timeout = config.get("test_settings", {}).get("authz_probe_timeout_seconds", 5)
    try:
        resp = httpx.get(f"{authz_cfg.base_url}/healthz", timeout=timeout)
    except httpx.HTTPError:
        return False
    return resp.is_success


@pytest.fixture(scope="session")
def authz_reachable(config) -> bool:
    """True iff the configured ``spark_authz.host`` answers /healthz."""
    return _spark_authz_reachable(config)


@pytest.fixture(scope="session")
def authz_client(config, authz_reachable) -> Generator[SparkAuthzClient, None, None]:
    """Direct spark-authz client. **Skips the test** if the host is unreachable.

    Take this only in tests that assert against SpiceDB directly. Tests that
    only exercise scale-agentex HTTP routes should NOT take this fixture —
    they degrade gracefully via ``optional_authz_client`` in the factories.

    Not every environment runs spark-authz (e.g. pubsec-dev runs raw SpiceDB
    without the spark-authz HTTP frontend).
    """
    if not authz_reachable:
        host = config["spark_authz"]["host"]
        pytest.skip(
            f"spark-authz unreachable at {host}. Tests that assert directly "
            "against SpiceDB are skipped. To run them, point ``spark_authz.host`` "
            "at a reachable spark-authz instance or set up a port-forward."
        )
    client = _build_authz_client(config)
    yield client
    client.close()


@pytest.fixture(scope="session")
def optional_authz_client(
    config, authz_reachable
) -> Generator[SparkAuthzClient | None, None, None]:
    """Like ``authz_client`` but returns ``None`` when unreachable instead of
    skipping. For cleanup-fallback paths that should still run when the
    SpiceDB side isn't available.
    """
    if not authz_reachable:
        yield None
        return
    client = _build_authz_client(config)
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@pytest.fixture()
def cleanup(request, config) -> Generator[CleanupTracker, None, None]:
    """Function-scoped cleanup tracker.

    Honors ``test_settings.cleanup_on_success`` and ``cleanup_on_failure``
    in config.json. Defaults: cleanup after pass + after fail.
    """
    tracker = CleanupTracker()
    yield tracker

    ts = config.get("test_settings", {})
    on_success = ts.get("cleanup_on_success", True)
    on_failure = ts.get("cleanup_on_failure", True)

    rep = getattr(request.node, "rep_call", None)
    if rep is None:
        tracker.execute()
        return

    if rep.skipped:
        if on_success:
            tracker.execute()
        return
    if rep.failed:
        if on_failure:
            tracker.execute()
        return
    if on_success:
        tracker.execute()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def create_agent(agentex_client_a, optional_authz_client, user_a, cleanup):
    """Factory: creates an agent as user_a and registers cleanup.

    Agents are the parent resource for api_keys; AGX1-325's authz checks
    cascade from this agent's tuples. The SpiceDB cleanup fallback only
    runs when spark-authz is reachable.

    Note: requires the caller to have ``agent.create`` on the tenant's
    ``agent:*`` wildcard. In environments where the test user lacks that
    permission (e.g. some shared dev clusters), use ``parent_agent``
    instead — it falls back to a pre-existing ``agentex.agent_id`` from
    config.json.
    """

    def _create(name: str | None = None) -> tuple[str, str]:
        agent_name = name or unique_agent_name()
        resp = agentex_client_a.create_agent(agent_name)
        assert resp.status_code in (
            200,
            201,
        ), f"Failed to create agent: {resp.status_code} {resp.text}"
        agent_id = resp.json()["id"]

        def _teardown():
            delete_resp = agentex_client_a.delete_agent(agent_id)
            if delete_resp.status_code not in (200, 204, 404):
                logger.warning(
                    "REST delete_agent failed (%d); SpiceDB owner tuple may leak",
                    delete_resp.status_code,
                )
            if optional_authz_client is not None:
                optional_authz_client.delete_resource(
                    AGENT_RESOURCE_TYPE, agent_id, user_a.identity_id
                )

        cleanup.add(f"delete agent {agent_id}", _teardown)
        return agent_id, agent_name

    return _create


@pytest.fixture()
def parent_agent(config, create_agent) -> tuple[str, str]:
    """Provides a parent agent for resource-under-test creation.

    Resolution order:
      1. If ``agentex.agent_id`` is set in config.json, use that pre-existing
         agent. Returns ``(agent_id, "<provided-via-config>")``. The user
         must already have api_key.create permission on this agent; no
         create-time authz is exercised in this mode.
      2. Otherwise, call ``create_agent()`` to mint a fresh one. Requires
         ``agent.create`` permission on the tenant.

    Use this fixture in tests that just need *some* agent to attach
    api_keys / events to. Take ``create_agent`` directly only when the
    test specifically asserts something about agent creation itself.
    """
    agentex_cfg = config.get("agentex") or {}
    provided_id = agentex_cfg.get("agent_id")
    if provided_id:
        logger.info(
            "Using pre-existing agent_id from config.json (skipping create_agent)"
        )
        return provided_id, "<provided-via-config>"
    return create_agent()


@pytest.fixture()
def create_ready_agent(agentex_client_a, optional_authz_client, user_a, cleanup):
    """Factory: creates a READY sync agent as user_a and registers cleanup.

    State/task tests need ``task/create`` to persist a task without forwarding
    to an ACP endpoint. A READY sync agent exercises the real RPC route while
    keeping the setup self-contained.
    """

    def _create(name: str | None = None) -> tuple[str, str]:
        agent_name = name or unique_agent_name("e2e-state-agent")
        resp = agentex_client_a.create_ready_agent(agent_name)
        assert resp.status_code in (
            200,
            201,
        ), f"Failed to create ready agent: {resp.status_code} {resp.text}"
        agent_id = resp.json()["id"]

        def _teardown():
            delete_resp = agentex_client_a.delete_agent(agent_id)
            if delete_resp.status_code not in (200, 204, 404):
                logger.warning(
                    "REST delete_agent failed (%d); SpiceDB owner tuple may leak",
                    delete_resp.status_code,
                )
            if optional_authz_client is not None:
                optional_authz_client.delete_resource(
                    AGENT_RESOURCE_TYPE, agent_id, user_a.identity_id
                )

        cleanup.add(f"delete ready agent {agent_id}", _teardown)
        return agent_id, agent_name

    return _create


@pytest.fixture()
def task_parent_agent(config, create_ready_agent) -> tuple[str, str]:
    agentex_cfg = config.get("agentex") or {}
    provided_id = agentex_cfg.get("agent_id")
    if provided_id:
        logger.info(
            "Using pre-existing agent_id from config.json for task/state tests"
        )
        return provided_id, "<provided-via-config>"
    return create_ready_agent()


@pytest.fixture()
def create_task(agentex_client_a, optional_authz_client, user_a, cleanup):
    """Factory: creates a task as user_a under the given agent."""

    def _create(agent_id: str, name: str | None = None) -> tuple[str, str]:
        task_name = name or unique_task_name()
        resp = agentex_client_a.create_task(
            agent_id=agent_id,
            name=task_name,
            task_metadata={"e2e_ticket": "AGX1-327"},
        )
        assert resp.status_code in (
            200,
            201,
        ), f"Failed to create task: {resp.status_code} {resp.text}"
        body = resp.json()
        assert "error" not in body, f"task/create returned JSON-RPC error: {body}"
        task_id = body["result"]["id"]

        def _teardown():
            delete_resp = agentex_client_a.delete_task(task_id)
            if delete_resp.status_code not in (200, 204, 404):
                logger.warning("REST delete_task returned %d", delete_resp.status_code)
            if optional_authz_client is not None:
                optional_authz_client.delete_resource(
                    TASK_RESOURCE_TYPE, task_id, user_a.identity_id
                )

        cleanup.add(f"delete task {task_id}", _teardown)
        return task_id, task_name

    return _create


@pytest.fixture()
def create_state(agentex_client_a, cleanup):
    """Factory: creates a state as user_a under the given task and agent."""

    def _create(task_id: str, agent_id: str, state: dict | None = None) -> str:
        resp = agentex_client_a.create_state(
            task_id=task_id,
            agent_id=agent_id,
            state=state or {"ticket": "AGX1-327"},
        )
        assert resp.status_code in (
            200,
            201,
        ), f"Failed to create state: {resp.status_code} {resp.text}"
        state_id = resp.json()["id"]

        def _teardown():
            delete_resp = agentex_client_a.delete_state(state_id)
            if delete_resp.status_code not in (200, 204, 404):
                logger.warning("REST delete_state returned %d", delete_resp.status_code)

        cleanup.add(f"delete state {state_id}", _teardown)
        return state_id

    return _create


@pytest.fixture()
def create_api_key(agentex_client_a, optional_authz_client, user_a, cleanup):
    """Factory: creates an api_key as user_a under the given agent.

    Returns ``(api_key_id, api_key_name, api_key_secret)``. Cleanup deletes
    via REST first; the SpiceDB DeleteResource fallback runs only when
    spark-authz is reachable.
    """

    def _create(agent_id: str, name: str | None = None) -> tuple[str, str, str]:
        api_key_name = name or unique_api_key_name()
        resp = agentex_client_a.create_api_key(agent_id=agent_id, name=api_key_name)
        assert resp.status_code in (
            200,
            201,
        ), f"Failed to create api_key: {resp.status_code} {resp.text}"
        body = resp.json()
        api_key_id = body["id"]
        api_key_secret = body["api_key"]

        def _teardown():
            delete_resp = agentex_client_a.delete_api_key(api_key_id)
            if delete_resp.status_code not in (200, 204, 404):
                logger.warning(
                    "REST delete_api_key returned %d", delete_resp.status_code
                )
            if optional_authz_client is not None:
                optional_authz_client.delete_resource(
                    API_KEY_RESOURCE_TYPE, api_key_id, user_a.identity_id
                )

        cleanup.add(f"delete api_key {api_key_id}", _teardown)
        return api_key_id, api_key_name, api_key_secret

    return _create
