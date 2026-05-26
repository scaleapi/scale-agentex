"""Integration tests for AgentAPIKeysUseCase dual-write to Spark AuthZ.

These cover the AGX1-272 dual-write path:

- Flag OFF: ``authorization_service.grant`` is NOT called and the api_key is
  written to the repository with creator metadata populated from the
  principal context.
- Flag ON: ``grant`` is called with ``AgentexResource.api_key(<id>)`` and the
  row is written.
- Delete deregisters: ``revoke`` is called when ``delete`` runs under the flag.
- Spark failure prevents row: when ``grant`` raises, the api_key is NOT
  persisted.
- Revoke failure does not block delete: when ``revoke`` raises, the DB
  delete still completes and the failure is logged.
- No creator → no grant: if neither user_id nor service_account_id is
  resolvable, the dual-write is a no-op (logged) and the row still lands.

The tests intentionally mock the repository, authorization service, agent
repository, and HTTP client. The behaviour under test is the call sequencing
inside ``AgentAPIKeysUseCase`` — not Postgres or Spark itself.

Note on structural divergence from the task PR (AGX1-274): tasks live behind
``AgentTaskService``; agent_api_keys have no service layer, so the dual-write
logic is colocated in ``AgentAPIKeysUseCase``. Mirrors the spirit of Asher's
PR rather than the exact layering.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from src.api.schemas.authorization_types import AgentexResource, AgentexResourceType
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.use_cases.agent_api_keys_use_case import AgentAPIKeysUseCase
from src.utils.feature_flags import FeatureFlagProvider
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


def _build_use_case(
    *,
    flag_accounts: str,
    principal: SimpleNamespace | None,
    grant: AsyncMock | None = None,
    revoke: AsyncMock | None = None,
    agent: AgentEntity | None = None,
    create_raises: Exception | None = None,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AgentAPIKeysUseCase, Mock, AsyncMock, AsyncMock]:
    monkeypatch.setenv("FGAC_AGENT_API_KEYS_DUAL_WRITE_ACCOUNTS", flag_accounts)

    sample_agent = agent or _agent()

    agent_repository = Mock()
    agent_repository.get = AsyncMock(return_value=sample_agent)

    agent_api_key_repository = Mock()
    if create_raises is None:
        agent_api_key_repository.create = AsyncMock(side_effect=lambda item: item)
    else:
        agent_api_key_repository.create = AsyncMock(side_effect=create_raises)
    agent_api_key_repository.delete = AsyncMock(return_value=None)
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
    authorization_service.grant = grant or AsyncMock(return_value={})
    authorization_service.revoke = revoke or AsyncMock(return_value=None)

    feature_flags = FeatureFlagProvider()

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
        feature_flags=feature_flags,
    )
    return (
        use_case,
        agent_api_key_repository,
        authorization_service.grant,
        authorization_service.revoke,
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_skips_grant_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _agent()
    use_case, repo, grant, _ = _build_use_case(
        flag_accounts="",
        principal=_principal(user_id="user-A", account_id="acct-1"),
        agent=agent,
        monkeypatch=monkeypatch,
    )

    api_key = await use_case.create(
        name="k1",
        agent_id=agent.id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="secret",
        account_id="acct-1",
    )

    grant.assert_not_called()
    repo.create.assert_awaited_once()
    assert api_key.creator_user_id == "user-A"
    assert api_key.creator_service_account_id is None
    assert api_key.spark_authz_zedtoken is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_calls_grant_when_flag_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _agent()
    use_case, repo, grant, _ = _build_use_case(
        flag_accounts="acct-1",
        principal=_principal(user_id="user-A", account_id="acct-1"),
        agent=agent,
        monkeypatch=monkeypatch,
    )

    api_key = await use_case.create(
        name="k1",
        agent_id=agent.id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="secret",
        account_id="acct-1",
    )

    grant.assert_awaited_once()
    granted_resource: AgentexResource = grant.await_args.kwargs["resource"]
    assert granted_resource.type == AgentexResourceType.api_key
    assert granted_resource.selector == api_key.id
    repo.create.assert_awaited_once()
    assert api_key.creator_user_id == "user-A"
    # Provider.spark.grant returns {} today — no zedtoken yet.
    assert api_key.spark_authz_zedtoken is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_api_key_calls_revoke_when_flag_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, repo, _, revoke = _build_use_case(
        flag_accounts="acct-1",
        principal=_principal(user_id="user-A", account_id="acct-1"),
        monkeypatch=monkeypatch,
    )

    api_key_id = orm_id()
    await use_case.delete(id=api_key_id, account_id="acct-1")

    repo.delete.assert_awaited_once_with(id=api_key_id)
    revoke.assert_awaited_once()
    revoked_resource: AgentexResource = revoke.await_args.kwargs["resource"]
    assert revoked_resource.type == AgentexResourceType.api_key
    assert revoked_resource.selector == api_key_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_api_key_skips_revoke_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, repo, _, revoke = _build_use_case(
        flag_accounts="",
        principal=_principal(user_id="user-A", account_id="acct-1"),
        monkeypatch=monkeypatch,
    )

    await use_case.delete(id=orm_id(), account_id="acct-1")

    repo.delete.assert_awaited_once()
    revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_grant_failure_prevents_db_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grant = AsyncMock(side_effect=RuntimeError("spark unavailable"))
    agent = _agent()
    use_case, repo, _, _ = _build_use_case(
        flag_accounts="acct-1",
        principal=_principal(user_id="user-A", account_id="acct-1"),
        grant=grant,
        agent=agent,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(RuntimeError, match="spark unavailable"):
        await use_case.create(
            name="k1",
            agent_id=agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="secret",
            account_id="acct-1",
        )

    repo.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_api_key_revoke_failure_does_not_block_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revoke = AsyncMock(side_effect=RuntimeError("spark unavailable"))
    use_case, repo, _, revoke_ref = _build_use_case(
        flag_accounts="acct-1",
        principal=_principal(user_id="user-A", account_id="acct-1"),
        revoke=revoke,
        monkeypatch=monkeypatch,
    )

    # Should NOT raise.
    await use_case.delete(id=orm_id(), account_id="acct-1")

    repo.delete.assert_awaited_once()
    revoke_ref.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_api_key_skips_grant_when_no_creator_resolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If neither user_id nor service_account_id is available on the principal,
    the dual-write is a no-op (logged) and the row still lands without a tuple."""
    agent = _agent()
    use_case, repo, grant, _ = _build_use_case(
        flag_accounts="acct-1",
        principal=_principal(user_id=None, account_id="acct-1"),
        agent=agent,
        monkeypatch=monkeypatch,
    )

    api_key = await use_case.create(
        name="k1",
        agent_id=agent.id,
        api_key_type=AgentAPIKeyType.EXTERNAL,
        api_key="secret",
        account_id="acct-1",
    )

    grant.assert_not_called()
    repo.create.assert_awaited_once()
    assert api_key.creator_user_id is None
    assert api_key.creator_service_account_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_by_agent_id_and_key_name_revokes_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _agent()
    existing_id = orm_id()
    use_case, repo, _, revoke = _build_use_case(
        flag_accounts="acct-1",
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
        account_id="acct-1",
    )

    repo.delete_by_agent_id_and_key_name.assert_awaited_once()
    revoke.assert_awaited_once()
    revoked_resource: AgentexResource = revoke.await_args.kwargs["resource"]
    assert revoked_resource.selector == existing_id
