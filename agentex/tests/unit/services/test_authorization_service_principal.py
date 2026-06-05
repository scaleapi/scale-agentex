"""Regression tests for principal resolution in ``AuthorizationService``.

The service uses an Ellipsis (``...``) sentinel to mean "principal not
supplied → authorize as the request's authenticated principal". A caller that
forwards an *optional, unset* request field (e.g. ``register_build`` passing
``request.principal_context``) hands the service an explicit ``None``. ``None``
is never a valid principal for the authz gateway (it rejects it), so the
service must treat ``None`` the same as the sentinel and fall back to the
authenticated principal. Without that, build-time agent registration 422s.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService

AUTHED = "authenticated-principal"
EXPLICIT = "explicit-principal"


def _service(gateway):
    """Build a service whose request carries an authenticated principal and
    no agent identity (so authorization is not bypassed)."""
    request = MagicMock()
    request.state.principal_context = AUTHED
    request.state.agent_identity = None
    return AuthorizationService(enabled=True, gateway=gateway, request=request)


@pytest.mark.unit
@pytest.mark.asyncio
class TestEffectivePrincipalCoalescing:
    """Both ``None`` and the sentinel fall back to the authenticated principal;
    an explicit principal is honored."""

    async def test_grant_none_falls_back_to_authenticated(self):
        gateway = MagicMock()
        gateway.grant = AsyncMock()
        svc = _service(gateway)

        await svc.grant(AgentexResource.agent("a-1"), principal_context=None)

        # The failing build-registration path: body field is None, must NOT be
        # forwarded as the principal.
        assert gateway.grant.await_args.args[0] == AUTHED

    async def test_grant_sentinel_uses_authenticated(self):
        gateway = MagicMock()
        gateway.grant = AsyncMock()
        svc = _service(gateway)

        await svc.grant(AgentexResource.agent("a-1"))

        assert gateway.grant.await_args.args[0] == AUTHED

    async def test_grant_explicit_principal_is_honored(self):
        gateway = MagicMock()
        gateway.grant = AsyncMock()
        svc = _service(gateway)

        await svc.grant(AgentexResource.agent("a-1"), principal_context=EXPLICIT)

        assert gateway.grant.await_args.args[0] == EXPLICIT

    async def test_revoke_none_falls_back_to_authenticated(self):
        gateway = MagicMock()
        gateway.revoke = AsyncMock()
        svc = _service(gateway)

        await svc.revoke(AgentexResource.agent("a-1"), principal_context=None)

        assert gateway.revoke.await_args.args[0] == AUTHED

    async def test_list_resources_none_falls_back_to_authenticated(self):
        gateway = MagicMock()
        gateway.list_resources = AsyncMock(return_value=[])
        svc = _service(gateway)

        await svc.list_resources(AgentexResourceType.agent, principal_context=None)

        assert gateway.list_resources.await_args.args[0] == AUTHED

    async def test_register_resource_none_falls_back_to_authenticated(self):
        gateway = MagicMock()
        gateway.register_resource = AsyncMock()
        svc = _service(gateway)

        await svc.register_resource(
            AgentexResource.agent("a-1"), principal_context=None
        )

        assert gateway.register_resource.await_args.args[0] == AUTHED

    async def test_check_none_falls_back_to_authenticated(self):
        gateway = MagicMock()
        gateway.check = AsyncMock(return_value=True)
        svc = _service(gateway)

        cache = MagicMock()
        cache.get_authorization_check = AsyncMock(return_value=None)  # cache miss
        cache.set_authorization_check = AsyncMock()

        with patch(
            "src.domain.services.authorization_service.get_auth_cache",
            AsyncMock(return_value=cache),
        ):
            await svc.check(
                AgentexResource.agent("*"),
                AuthorizedOperationType.create,
                principal_context=None,
            )

        assert gateway.check.await_args.args[0] == AUTHED
