"""Tests for deployment route authorization."""

from __future__ import annotations

from inspect import signature
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.api.routes.deployments import list_deployments
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)


def _dep_callable(annotation):
    """Pull the FastAPI dependency function out of an ``Annotated[str, Depends(...)]``."""
    return annotation.__metadata__[0].dependency


@pytest.mark.unit
@pytest.mark.asyncio
class TestListDeploymentsAuthz:
    async def test_agent_id_requires_agent_read_authorization(self):
        annotation = signature(list_deployments).parameters["agent_id"].annotation
        dep = _dep_callable(annotation)

        authorization = MagicMock()
        authorization.check = AsyncMock(return_value=True)

        result = await dep(
            authorization,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            "agent-1",
        )

        assert result == "agent-1"
        authorization.check.assert_awaited_once_with(
            resource=AgentexResource(
                type=AgentexResourceType.agent,
                selector="agent-1",
            ),
            operation=AuthorizedOperationType.read,
        )
