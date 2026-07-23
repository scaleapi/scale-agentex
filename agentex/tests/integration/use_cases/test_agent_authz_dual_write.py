"""Integration tests for agent authorization-graph lifecycle writes.

- ``register_agent`` / ``register_build`` ``register_resource`` the agent (with no
  parent — an agent's tenant edge is server-derived) *before* persisting the row,
  but only on a genuine create. The update / name-already-exists paths must not
  register, or the owner would be rewritten to the current caller.
- If the persist fails (or loses a duplicate race) after a successful register,
  the create issues a compensating ``deregister_resource`` and re-raises / adopts
  the existing row. Explicit ownership grant/revoke calls are route-level behavior.
- If registration was skipped because no creator was resolvable, failed creates
  do not issue a compensating deregister for a resource that was never registered.
- ``delete`` ``deregister_resource``s *after* the soft-delete, best-effort: a
  failure is swallowed so a delete that already succeeded never surfaces an error.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.api.schemas.authorization_types import AgentexResource, AgentexResourceType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.use_cases.agents_use_case import AgentsUseCase

from tests.fixtures.services import make_noop_authorization_service


def _principal(
    user_id: str | None = "user-A", service_account_id: str | None = None
) -> SimpleNamespace:
    """Minimal stand-in for the auth principal context."""
    return SimpleNamespace(user_id=user_id, service_account_id=service_account_id)


def _build_use_case(
    *,
    agent_repository,
    deployment_history_repository=None,
    deployment_repository=None,
    principal: SimpleNamespace | None = None,
) -> tuple[AgentsUseCase, Mock]:
    authorization_service = make_noop_authorization_service()
    # Resolvable creator by default so the create path registers; tests that
    # exercise the no-creator guard pass a principal with no user/service account.
    authorization_service.principal_context = (
        principal if principal is not None else _principal()
    )
    use_case = AgentsUseCase(
        agent_repository=agent_repository,
        deployment_history_repository=deployment_history_repository or AsyncMock(),
        deployment_repository=deployment_repository or AsyncMock(),
        temporal_adapter=AsyncMock(),
        authorization_service=authorization_service,
    )
    return use_case, authorization_service


def _existing_agent(name: str) -> AgentEntity:
    return AgentEntity(
        id=str(uuid4()),
        name=name,
        description="existing agent",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://existing-acp",
    )


async def _agent_exists(agent_repository, agent_id: str) -> bool:
    try:
        await agent_repository.get(id=agent_id)
        return True
    except ItemDoesNotExist:
        return False


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentRegisterOnCreate:
    async def test_create_registers_before_persist_with_no_parent(
        self, isolated_repositories
    ):
        agent_repo = isolated_repositories["agent_repository"]
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
            deployment_repository=isolated_repositories["deployment_repository"],
        )

        # When register fires, the Postgres row must not exist yet — this is
        # what makes a registration failure abort the request cleanly.
        observed = {}

        async def _record_existence(resource, parent=None, *, principal_context=None):
            observed["row_exists_at_register"] = await _agent_exists(
                agent_repo, resource.selector
            )

        authorization_service.register_resource.side_effect = _record_existence

        agent = await use_case.register_agent(
            name=f"dw-create-{uuid4().hex[:8]}",
            description="created via ownership-write test",
            acp_url="http://new-acp",
        )

        assert observed["row_exists_at_register"] is False
        assert await _agent_exists(agent_repo, agent.id) is True

        authorization_service.register_resource.assert_awaited_once()
        call = authorization_service.register_resource.call_args
        registered_resource: AgentexResource = call.args[0]
        assert registered_resource.type == AgentexResourceType.agent
        assert registered_resource.selector == agent.id
        # An agent's tenant edge is server-derived from the account; no parent.
        assert call.kwargs.get("parent") is None
        assert len(call.args) == 1
        # Ownership is granted by the route after create succeeds.
        authorization_service.grant.assert_not_awaited()

    async def test_register_failure_aborts_create_with_no_row(
        self, isolated_repositories
    ):
        agent_repo = isolated_repositories["agent_repository"]
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
            deployment_repository=isolated_repositories["deployment_repository"],
        )
        authorization_service.register_resource.side_effect = RuntimeError("authz down")

        name = f"dw-register-fail-{uuid4().hex[:8]}"
        with pytest.raises(RuntimeError):
            await use_case.register_agent(
                name=name,
                description="should never persist",
                acp_url="http://new-acp",
            )

        # No compensation needed: the persist never ran, so no row exists.
        with pytest.raises(ItemDoesNotExist):
            await agent_repo.get(name=name)
        authorization_service.deregister_resource.assert_not_awaited()

    async def test_persist_failure_compensates_and_surfaces_original_error(self):
        # Register succeeds, then the Postgres persist blows up. The create must
        # deregister the just-registered agent (no orphan) and re-raise the
        # ORIGINAL persist error, not any deregister error.
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        agent_repo.create = AsyncMock(side_effect=RuntimeError("db down"))
        use_case, authorization_service = _build_use_case(agent_repository=agent_repo)

        with pytest.raises(RuntimeError, match="db down"):
            await use_case.register_agent(
                name=f"dw-persist-fail-{uuid4().hex[:8]}",
                description="persist fails",
                acp_url="http://new-acp",
            )

        authorization_service.register_resource.assert_awaited_once()
        # deregister compensates the register; ownership writes are route-level.
        authorization_service.deregister_resource.assert_awaited_once()
        authorization_service.grant.assert_not_awaited()
        authorization_service.revoke.assert_not_awaited()
        registered = authorization_service.register_resource.call_args.args[0]
        compensated = authorization_service.deregister_resource.call_args.args[0]
        assert compensated.type == AgentexResourceType.agent
        assert compensated.selector == registered.selector

    async def test_duplicate_compensates_then_adopts_existing_row(self):
        # A parallel writer wins the create. The use case deregisters its own
        # registration and adopts the already-persisted row.
        existing = _existing_agent(f"dw-dup-{uuid4().hex[:8]}")
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=[ItemDoesNotExist("absent"), existing])
        agent_repo.create = AsyncMock(side_effect=DuplicateItemError("exists"))
        use_case, authorization_service = _build_use_case(agent_repository=agent_repo)

        result = await use_case.register_agent(
            name=existing.name,
            description="dup create",
            acp_url="http://new-acp",
        )

        assert result.id == existing.id
        authorization_service.register_resource.assert_awaited_once()
        authorization_service.deregister_resource.assert_awaited_once()
        authorization_service.grant.assert_not_awaited()
        authorization_service.revoke.assert_not_awaited()
        registered = authorization_service.register_resource.call_args.args[0]
        compensated = authorization_service.deregister_resource.call_args.args[0]
        assert compensated.selector == registered.selector

    async def test_update_path_does_not_register(self):
        # register_agent called with an agent_id is an update, not a create: it
        # must NOT register, or ownership would be rewritten to the caller.
        existing = _existing_agent(f"dw-update-{uuid4().hex[:8]}")
        agent_repo = Mock()
        agent_repo.get = AsyncMock(return_value=existing)
        agent_repo.update = AsyncMock(return_value=existing)
        use_case, authorization_service = _build_use_case(agent_repository=agent_repo)

        await use_case.register_agent(
            name=existing.name,
            description="updated description",
            acp_url="http://updated-acp",
            agent_id=existing.id,
        )

        authorization_service.register_resource.assert_not_awaited()
        authorization_service.grant.assert_not_awaited()

    async def test_create_without_resolvable_creator_skips_register(
        self, isolated_repositories
    ):
        # With no user or service account on the principal there is no owner to
        # attribute, so the create persists the row but skips registration.
        agent_repo = isolated_repositories["agent_repository"]
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
            deployment_repository=isolated_repositories["deployment_repository"],
            principal=_principal(user_id=None, service_account_id=None),
        )

        agent = await use_case.register_agent(
            name=f"dw-no-creator-{uuid4().hex[:8]}",
            description="no resolvable creator",
            acp_url="http://new-acp",
        )

        authorization_service.register_resource.assert_not_awaited()
        authorization_service.grant.assert_not_awaited()
        assert await _agent_exists(agent_repo, agent.id) is True

    async def test_persist_failure_without_resolvable_creator_skips_compensation(self):
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        agent_repo.create = AsyncMock(side_effect=RuntimeError("db down"))
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            principal=_principal(user_id=None, service_account_id=None),
        )

        with pytest.raises(RuntimeError, match="db down"):
            await use_case.register_agent(
                name=f"dw-no-creator-fail-{uuid4().hex[:8]}",
                description="persist fails after skipped register",
                acp_url="http://new-acp",
            )

        authorization_service.register_resource.assert_not_awaited()
        authorization_service.deregister_resource.assert_not_awaited()
        authorization_service.grant.assert_not_awaited()
        authorization_service.revoke.assert_not_awaited()

    async def test_create_falls_back_to_body_principal_when_middleware_missing(
        self,
    ):
        # Pod self-registration via whitelisted /agents/register clears the
        # middleware principal, so the SDK ships the manifest-declared identity
        # in the request body. The use case must accept that body principal so
        # ownership is still minted from the manifest identity — otherwise the
        # agent registers but has no owner tuple and is invisible to the UI.
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        agent_repo.create = AsyncMock(side_effect=lambda item: item)
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            principal=_principal(user_id=None, service_account_id=None),
        )

        # Dict shape matches what /v1/authn returns and what the SDK decodes
        # from AUTH_PRINCIPAL_B64 (see scale-agentex-python registration.py).
        body_principal = {
            "service_account_id": "sa-from-manifest",
            "account_id": "acct-1",
        }

        agent = await use_case.register_agent(
            name=f"dw-body-fallback-{uuid4().hex[:8]}",
            description="body principal fallback",
            acp_url="http://new-acp",
            body_principal_context=body_principal,
        )

        authorization_service.register_resource.assert_awaited_once()
        call = authorization_service.register_resource.call_args
        registered_resource: AgentexResource = call.args[0]
        assert registered_resource.type == AgentexResourceType.agent
        assert registered_resource.selector == agent.id
        # The body principal must be forwarded to the gateway so it doesn't
        # fall back to the (unset) middleware principal.
        assert call.kwargs.get("principal_context") == body_principal

    async def test_middleware_principal_takes_precedence_over_body(self):
        # An authenticated caller (via CLI/UI) sets the middleware principal.
        # Even if a body principal is also sent, the authenticated identity
        # from the middleware must win — the body is only a fallback for the
        # whitelisted pod path.
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        agent_repo.create = AsyncMock(side_effect=lambda item: item)
        middleware_principal = _principal(user_id="user-from-middleware")
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            principal=middleware_principal,
        )

        body_principal = {"service_account_id": "sa-should-not-win"}

        await use_case.register_agent(
            name=f"dw-middleware-wins-{uuid4().hex[:8]}",
            description="middleware principal wins",
            acp_url="http://new-acp",
            body_principal_context=body_principal,
        )

        authorization_service.register_resource.assert_awaited_once()
        call = authorization_service.register_resource.call_args
        assert call.kwargs.get("principal_context") is middleware_principal


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentRegisterBuildOnCreate:
    async def test_build_persist_failure_compensates_and_surfaces_original_error(self):
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        agent_repo.create = AsyncMock(side_effect=RuntimeError("db down"))
        use_case, authorization_service = _build_use_case(agent_repository=agent_repo)

        with pytest.raises(RuntimeError, match="db down"):
            await use_case.register_build(
                name=f"dw-build-persist-fail-{uuid4().hex[:8]}",
                description="build persist fails",
            )

        authorization_service.register_resource.assert_awaited_once()
        authorization_service.deregister_resource.assert_awaited_once()
        authorization_service.grant.assert_not_awaited()
        authorization_service.revoke.assert_not_awaited()
        registered = authorization_service.register_resource.call_args.args[0]
        compensated = authorization_service.deregister_resource.call_args.args[0]
        assert compensated.type == AgentexResourceType.agent
        assert compensated.selector == registered.selector

    async def test_build_duplicate_compensates_then_adopts_existing_row(self):
        existing = _existing_agent(f"dw-build-dup-{uuid4().hex[:8]}")
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=[ItemDoesNotExist("absent"), existing])
        agent_repo.create = AsyncMock(side_effect=DuplicateItemError("exists"))
        use_case, authorization_service = _build_use_case(agent_repository=agent_repo)

        result = await use_case.register_build(
            name=existing.name,
            description="dup build create",
        )

        assert result.id == existing.id
        authorization_service.register_resource.assert_awaited_once()
        authorization_service.deregister_resource.assert_awaited_once()
        authorization_service.grant.assert_not_awaited()
        authorization_service.revoke.assert_not_awaited()
        registered = authorization_service.register_resource.call_args.args[0]
        compensated = authorization_service.deregister_resource.call_args.args[0]
        assert compensated.selector == registered.selector

    async def test_build_without_resolvable_creator_skips_register(
        self, isolated_repositories
    ):
        agent_repo = isolated_repositories["agent_repository"]
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
            deployment_repository=isolated_repositories["deployment_repository"],
            principal=_principal(user_id=None, service_account_id=None),
        )

        agent = await use_case.register_build(
            name=f"dw-build-no-creator-{uuid4().hex[:8]}",
            description="build no resolvable creator",
        )

        authorization_service.register_resource.assert_not_awaited()
        authorization_service.grant.assert_not_awaited()
        assert await _agent_exists(agent_repo, agent.id) is True

    async def test_build_persist_failure_without_resolvable_creator_skips_compensation(
        self,
    ):
        agent_repo = Mock()
        agent_repo.get = AsyncMock(side_effect=ItemDoesNotExist("absent"))
        agent_repo.create = AsyncMock(side_effect=RuntimeError("db down"))
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            principal=_principal(user_id=None, service_account_id=None),
        )

        with pytest.raises(RuntimeError, match="db down"):
            await use_case.register_build(
                name=f"dw-build-no-creator-fail-{uuid4().hex[:8]}",
                description="build persist fails after skipped register",
            )

        authorization_service.register_resource.assert_not_awaited()
        authorization_service.deregister_resource.assert_not_awaited()
        authorization_service.grant.assert_not_awaited()
        authorization_service.revoke.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentDeregisterOnDelete:
    async def test_delete_deregisters_after_soft_delete(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
            deployment_repository=isolated_repositories["deployment_repository"],
        )
        agent = await use_case.register_agent(
            name=f"dw-del-{uuid4().hex[:8]}",
            description="to be deleted",
            acp_url="http://new-acp",
        )
        authorization_service.deregister_resource.reset_mock()

        deleted = await use_case.delete(id=agent.id)

        assert deleted.status == AgentStatus.DELETED
        persisted = await agent_repo.get(id=agent.id)
        assert persisted.status == AgentStatus.DELETED
        authorization_service.deregister_resource.assert_awaited_once()
        deregistered: AgentexResource = (
            authorization_service.deregister_resource.call_args.args[0]
        )
        assert deregistered.type == AgentexResourceType.agent
        assert deregistered.selector == agent.id
        # Ownership is revoked by the route after delete succeeds.
        authorization_service.revoke.assert_not_awaited()

    async def test_delete_swallows_deregister_failure(self, isolated_repositories):
        # A deregister failure after a successful soft-delete must not surface:
        # Postgres is the source of truth for existence.
        agent_repo = isolated_repositories["agent_repository"]
        use_case, authorization_service = _build_use_case(
            agent_repository=agent_repo,
            deployment_history_repository=isolated_repositories[
                "deployment_history_repository"
            ],
            deployment_repository=isolated_repositories["deployment_repository"],
        )
        agent = await use_case.register_agent(
            name=f"dw-del-fail-{uuid4().hex[:8]}",
            description="delete with failing deregister",
            acp_url="http://new-acp",
        )
        authorization_service.deregister_resource.reset_mock()
        authorization_service.deregister_resource.side_effect = RuntimeError(
            "authz down"
        )

        # Must not raise despite the deregister failure.
        deleted = await use_case.delete(id=agent.id)

        assert deleted.status == AgentStatus.DELETED
        persisted = await agent_repo.get(id=agent.id)
        assert persisted.status == AgentStatus.DELETED
        authorization_service.deregister_resource.assert_awaited_once()
