"""Integration tests for AgentAPIKeysUseCase dual-write to Spark AuthZ.

These cover the AGX1-272 dual-write path. scale-agentex calls
``register_resource`` / ``deregister_resource`` unconditionally; per-account
routing (Spark vs legacy SGP) is owned by agentex-auth (scaleapi/agentex#353)
so scale-agentex does NOT couple to egp-api-backend's feature-flag service.

- Create calls register_resource with parent=agent (the parent_agent edge
  is load-bearing for the SpiceDB cascade).
- Delete calls deregister_resource after the Postgres row is gone.
- Spark failure prevents row: when register_resource raises, the api_key
  is NOT persisted.
- Deregister failure does not block delete: when deregister_resource
  raises, the DB delete still completes and the failure is logged.
- No creator → no register: if neither user_id nor service_account_id is
  resolvable, the dual-write is a no-op (logged) and the row still lands.

The tests intentionally mock the repository, authorization service, agent
repository, and HTTP client. The behaviour under test is the call sequencing
inside ``AgentAPIKeysUseCase`` — not Postgres or Spark itself.

Note on structural divergence from the task PR (AGX1-274): tasks live behind
``AgentTaskService``; agent_api_keys have no service layer, so the dual-write
logic is colocated in ``AgentAPIKeysUseCase``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import AgentexResource, AgentexResourceType
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.use_cases.agent_api_keys_use_case import AgentAPIKeysUseCase
from src.utils.ids import orm_id


def _principal(user_id: str | None, account_id: str | None) -> SimpleNamespace:
    """Minimal stand-in for AgentexAuthPrincipalContext."""
    return SimpleNamespace(
        user_id=user_id, service_account_id=None, account_id=account_id
    )


def _agent() -> AgentEntity:
    agent_id = orm_id()
    return AgentEntity(
        id=agent_id,
        name=f"agent-{agent_id[:8]}",
        description="dual-write test agent",
        status=AgentStatus.READY,
        acp_type=ACPType.SYNC,
        acp_url="http://test-acp",
    )


def _stub_api_key(id: str) -> AgentAPIKeyEntity:
    """Minimal entity stand-in for the repo.get default in _build_use_case."""
    return AgentAPIKeyEntity(
        id=id,
        name="stub",
        agent_id=orm_id(),
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="stub",
    )


def _build_use_case(
    *,
    principal: SimpleNamespace | None,
    register_resource: AsyncMock | None = None,
    deregister_resource: AsyncMock | None = None,
    agent: AgentEntity | None = None,
    create_raises: Exception | None = None,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AgentAPIKeysUseCase, Mock, AsyncMock, AsyncMock]:
    sample_agent = agent or _agent()

    agent_repository = Mock()
    agent_repository.get = AsyncMock(return_value=sample_agent)

    agent_api_key_repository = Mock()
    if create_raises is None:
        agent_api_key_repository.create = AsyncMock(side_effect=lambda item: item)
    else:
        agent_api_key_repository.create = AsyncMock(side_effect=create_raises)
    agent_api_key_repository.delete = AsyncMock(return_value=None)
    # Default get() returns a sentinel "exists" so delete() flows through the
    # deregister path; tests covering "row doesn't exist" override this.
    agent_api_key_repository.get = AsyncMock(side_effect=lambda id: _stub_api_key(id))
    agent_api_key_repository.get_by_agent_id_and_name = AsyncMock(return_value=None)
    agent_api_key_repository.get_by_agent_name_and_key_name = AsyncMock(
        return_value=None
    )
    agent_api_key_repository.delete_by_agent_id_and_key_name = AsyncMock(
        return_value=None
    )
    agent_api_key_repository.delete_by_agent_name_and_key_name = AsyncMock(
        return_value=None
    )

    authorization_service = Mock()
    authorization_service.principal_context = principal
    authorization_service.register_resource = register_resource or AsyncMock(
        return_value=None
    )
    authorization_service.deregister_resource = deregister_resource or AsyncMock(
        return_value=None
    )

    # Patch env var lookup inside UseCase __init__ so we don't depend on real
    # env configuration to instantiate.
    monkeypatch.setenv("AGENTEX_AUTH_URL", "")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("WEBHOOK_REQUEST_TIMEOUT", "10")

    use_case = AgentAPIKeysUseCase(
        agent_api_key_repository=agent_api_key_repository,
        agent_repository=agent_repository,
        client=Mock(),
        authorization_service=authorization_service,
    )
    return (
        use_case,
        agent_api_key_repository,
        authorization_service.register_resource,
        authorization_service.deregister_resource,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_calls_register_resource_with_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _agent()
    use_case, repo, register, _ = _build_use_case(
        principal=_principal(user_id="user-A", account_id="acct-1"),
        agent=agent,
        monkeypatch=monkeypatch,
    )

    api_key = await use_case.create(
        name="k1",
        agent_id=agent.id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="secret",
    )

    register.assert_awaited_once()
    registered_resource: AgentexResource = register.await_args.kwargs["resource"]
    assert registered_resource.type == AgentexResourceType.api_key
    assert registered_resource.selector == api_key.id
    # parent_agent edge is load-bearing — without it the SpiceDB cascade
    # `read = ... & parent_agent->read & ...` fails closed for every reader.
    registered_parent: AgentexResource = register.await_args.kwargs["parent"]
    assert registered_parent is not None
    assert registered_parent.type == AgentexResourceType.agent
    assert registered_parent.selector == agent.id
    repo.create.assert_awaited_once()
    # Sanity: the persisted entity itself; we don't persist creator audit
    # columns in OSS scale-agentex (Harvey's review feedback on #248).
    assert api_key.id is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_api_key_calls_deregister_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, repo, _, deregister = _build_use_case(
        principal=_principal(user_id="user-A", account_id="acct-1"),
        monkeypatch=monkeypatch,
    )

    api_key_id = orm_id()
    await use_case.delete(id=api_key_id)

    repo.delete.assert_awaited_once_with(id=api_key_id)
    deregister.assert_awaited_once()
    deregistered_resource: AgentexResource = deregister.await_args.kwargs["resource"]
    assert deregistered_resource.type == AgentexResourceType.api_key
    assert deregistered_resource.selector == api_key_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_grant_failure_prevents_db_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_resource = AsyncMock(side_effect=RuntimeError("spark unavailable"))
    agent = _agent()
    use_case, repo, _, _ = _build_use_case(
        principal=_principal(user_id="user-A", account_id="acct-1"),
        register_resource=register_resource,
        agent=agent,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(RuntimeError, match="spark unavailable"):
        await use_case.create(
            name="k1",
            agent_id=agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="secret",
        )

    repo.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_api_key_revoke_failure_does_not_block_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deregister = AsyncMock(side_effect=RuntimeError("spark unavailable"))
    use_case, repo, _, deregister_ref = _build_use_case(
        principal=_principal(user_id="user-A", account_id="acct-1"),
        deregister_resource=deregister,
        monkeypatch=monkeypatch,
    )

    # Should NOT raise.
    await use_case.delete(id=orm_id())

    repo.delete.assert_awaited_once()
    deregister_ref.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_skips_grant_when_no_creator_resolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If neither user_id nor service_account_id is available on the principal,
    the dual-write is a no-op (logged) and the row still lands without a tuple."""
    agent = _agent()
    use_case, repo, register, _ = _build_use_case(
        principal=_principal(user_id=None, account_id="acct-1"),
        agent=agent,
        monkeypatch=monkeypatch,
    )

    api_key = await use_case.create(
        name="k1",
        agent_id=agent.id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="secret",
    )

    register.assert_not_called()
    repo.create.assert_awaited_once()
    # Sanity: the row landed even though we skipped the auth-side registration.
    assert api_key.id is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_by_agent_id_and_key_name_revokes_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _agent()
    existing_id = orm_id()
    use_case, repo, _, deregister = _build_use_case(
        principal=_principal(user_id="user-A", account_id="acct-1"),
        agent=agent,
        monkeypatch=monkeypatch,
    )
    repo.get_by_agent_id_and_name = AsyncMock(
        return_value=AgentAPIKeyEntity(
            id=existing_id,
            agent_id=agent.id,
            name="k1",
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="secret",
        )
    )

    await use_case.delete_by_agent_id_and_key_name(
        agent_id=agent.id,
        key_name="k1",
        api_key_type=AgentAPIKeyType.EXTERNAL,
    )

    repo.delete_by_agent_id_and_key_name.assert_awaited_once()
    deregister.assert_awaited_once()
    deregistered_resource: AgentexResource = deregister.await_args.kwargs["resource"]
    assert deregistered_resource.selector == existing_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_api_key_skips_deregister_when_row_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the api_key id doesn't exist, the pre-fetch raises and the
    deregister call is skipped — matches the delete_by_* pattern and avoids
    a wasted auth round-trip on a no-op delete."""
    use_case, repo, _, deregister = _build_use_case(
        principal=_principal(user_id="user-A", account_id="acct-1"),
        monkeypatch=monkeypatch,
    )
    # Override the default "row exists" sentinel.
    repo.get = AsyncMock(side_effect=ItemDoesNotExist("not found"))

    await use_case.delete(id=orm_id())

    repo.delete.assert_awaited_once()
    deregister.assert_not_called()
