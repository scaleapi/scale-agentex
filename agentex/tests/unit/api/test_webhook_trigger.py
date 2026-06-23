"""Unit tests for the POST /agent_api_keys/webhook-trigger convenience endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import src.api.routes.agent_api_keys as mod
from fastapi import HTTPException
from src.api.routes.agent_api_keys import create_webhook_trigger
from src.api.schemas.agent_api_keys import CreateWebhookTriggerRequest
from src.domain.entities.agent_api_keys import AgentAPIKeyType


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateWebhookTrigger:
    async def _call(self, monkeypatch, request, *, existing=None, base_env=None):
        # The agent-authorization helper does real authz work; stub it to a no-op.
        monkeypatch.setattr(mod, "_check_agent_or_collapse_to_404", AsyncMock())
        if base_env is not None:
            monkeypatch.setenv("AGENTEX_PUBLIC_URL", base_env)
        else:
            monkeypatch.delenv("AGENTEX_PUBLIC_URL", raising=False)

        agent_use_case = MagicMock()
        agent_use_case.get = AsyncMock(return_value=MagicMock(id="agent-1"))

        akuc = MagicMock()
        akuc.get_by_agent_id_and_name = AsyncMock(return_value=existing)
        akuc.create = AsyncMock(
            return_value=MagicMock(id="key-1", api_key_type=request.source)
        )

        resp = await create_webhook_trigger(
            request=request,
            agent_api_key_use_case=akuc,
            agent_use_case=agent_use_case,
            authorization_service=MagicMock(),
        )
        return resp, akuc

    async def test_creates_key_and_composes_url(self, monkeypatch):
        req = CreateWebhookTriggerRequest(
            agent_name="golden-agent",
            source=AgentAPIKeyType.GITHUB,
            name="acme/widgets",
            forward_path="github-pr/cfg-9",
        )
        resp, akuc = await self._call(
            monkeypatch, req, base_env="https://sgp.example.com"
        )

        assert len(resp.secret) >= 32  # auto-generated signing secret
        assert (
            resp.webhook_url
            == "https://sgp.example.com/agents/forward/name/golden-agent/github-pr/cfg-9"
        )
        assert resp.webhook_path == "/agents/forward/name/golden-agent/github-pr/cfg-9"
        assert resp.source == AgentAPIKeyType.GITHUB
        # key registered under the signature-lookup name + type
        assert akuc.create.await_args.kwargs["name"] == "acme/widgets"
        assert akuc.create.await_args.kwargs["api_key_type"] == AgentAPIKeyType.GITHUB
        assert akuc.create.await_args.kwargs["api_key"] == resp.secret

    async def test_uses_provided_secret_and_no_url_without_base(self, monkeypatch):
        req = CreateWebhookTriggerRequest(
            agent_name="a",
            source=AgentAPIKeyType.GITHUB,
            name="o/r",
            forward_path="gh",
            secret="mysecret",
        )
        resp, _ = await self._call(monkeypatch, req)
        assert resp.secret == "mysecret"
        assert resp.webhook_url is None  # no AGENTEX_PUBLIC_URL configured
        assert resp.webhook_path == "/agents/forward/name/a/gh"

    async def test_conflict_when_key_exists(self, monkeypatch):
        req = CreateWebhookTriggerRequest(
            agent_name="a", source=AgentAPIKeyType.GITHUB, name="o/r", forward_path="gh"
        )
        with pytest.raises(HTTPException) as exc:
            await self._call(monkeypatch, req, existing=MagicMock())
        assert exc.value.status_code == 409

    async def test_rejects_non_webhook_source(self):
        req = CreateWebhookTriggerRequest(
            agent_name="a", source=AgentAPIKeyType.EXTERNAL, name="x", forward_path="gh"
        )
        with pytest.raises(HTTPException) as exc:
            await create_webhook_trigger(
                request=req,
                agent_api_key_use_case=MagicMock(),
                agent_use_case=MagicMock(),
                authorization_service=MagicMock(),
            )
        assert exc.value.status_code == 400

    async def test_slack_without_secret_rejected(self, monkeypatch):
        # Slack signs with the app's existing Signing Secret — we can't generate one,
        # so omitting it must 400 rather than store a random value that never matches.
        req = CreateWebhookTriggerRequest(
            agent_name="a", source=AgentAPIKeyType.SLACK, name="my-app", forward_path="slack"
        )
        with pytest.raises(HTTPException) as exc:
            await self._call(monkeypatch, req)
        assert exc.value.status_code == 400

    async def test_slack_with_provided_secret_ok(self, monkeypatch):
        req = CreateWebhookTriggerRequest(
            agent_name="a",
            source=AgentAPIKeyType.SLACK,
            name="my-app",
            forward_path="slack",
            secret="slack-signing-secret",
        )
        resp, akuc = await self._call(monkeypatch, req)
        assert resp.secret == "slack-signing-secret"
        assert akuc.create.await_args.kwargs["api_key"] == "slack-signing-secret"
