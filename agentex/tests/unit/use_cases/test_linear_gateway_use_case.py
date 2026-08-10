"""Unit tests for the Linear gateway — everything that does NOT require a real Linear
app: signature verification, AgentSessionEvent normalization, the handle_linear_event
control flow (dev-skip / drop / dedup / ack), dispatch (ACP mocked), acting identity,
and agentActivityCreate delivery with client-credentials token minting (httpx mocked).
"""

import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks
from src.domain.entities.agents_rpc import AgentRPCMethod
from src.domain.use_cases import linear_gateway_use_case as lg
from src.domain.use_cases.linear_gateway_use_case import (
    LinearGatewayUseCase,
    Target,
    normalize,
    verify_signature,
)


def _sig(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _created_payload(comment="math-agent please help", session="sess_1"):
    return {
        "type": "AgentSessionEvent",
        "action": "created",
        "webhookTimestamp": _now_ms(),
        "agentSession": {
            "id": session,
            "issue": {"id": "iss_1", "title": "Fix the bug", "description": "it broke"},
            "comment": {"body": comment},
        },
    }


@pytest.fixture(autouse=True)
def _no_runtime_agents(monkeypatch):
    """Default: no selector names a registered agent, so resolution falls to
    golden-agent (no DB hit). Non-golden routing tests override this."""
    monkeypatch.setattr(
        LinearGatewayUseCase, "_get_agent_by_name", AsyncMock(return_value=None)
    )


@pytest.mark.unit
class TestVerifySignature:
    def test_valid_signature_passes(self):
        secret, body = "shh", b'{"x":1}'
        assert verify_signature(secret, _sig(secret, body), body, _now_ms()) is True

    def test_wrong_signature_fails(self):
        body = b'{"x":1}'
        assert verify_signature("shh", _sig("other", body), body, _now_ms()) is False

    def test_stale_timestamp_fails(self):
        secret, body = "shh", b'{"x":1}'
        stale = _now_ms() - 10 * 60 * 1000  # 10 min old > 60s guard
        assert verify_signature(secret, _sig(secret, body), body, stale) is False

    def test_nonnumeric_timestamp_fails(self):
        assert verify_signature("shh", "deadbeef", b"{}", "not-a-number") is False

    def test_empty_secret_fails_closed(self):
        # An empty HMAC key is publicly known — even a "correctly" computed signature
        # over the empty key must be rejected, or an unconfigured secret authenticates
        # every forged delivery.
        body = b'{"x":1}'
        assert verify_signature("", _sig("", body), body, _now_ms()) is False


@pytest.mark.unit
class TestNormalize:
    def test_created_extracts_session_prompt_and_selector(self):
        inb = normalize(_created_payload())
        assert inb.session_id == "sess_1"
        assert inb.issue_id == "iss_1"
        assert inb.action == "created"
        assert inb.selector == "math-agent"  # first token of the comment
        assert "please help" in inb.text

    def test_created_falls_back_to_issue_when_no_comment(self):
        p = _created_payload()
        p["agentSession"].pop("comment")
        inb = normalize(p)
        assert "Fix the bug" in inb.text and "it broke" in inb.text

    def test_prompted_reads_agent_activity_body(self):
        p = {
            "type": "AgentSessionEvent",
            "action": "prompted",
            "agentSession": {"id": "sess_1"},
            "agentActivity": {"body": "any update?"},
        }
        inb = normalize(p)
        assert inb.action == "prompted"
        assert inb.text == "any update?"

    def test_ignores_non_agent_session_events(self):
        assert normalize({"type": "Issue", "action": "create"}) is None

    def test_ignores_unhandled_actions(self):
        assert normalize({"type": "AgentSessionEvent", "action": "elicited"}) is None

    def test_ignores_missing_session_id(self):
        assert (
            normalize(
                {"type": "AgentSessionEvent", "action": "created", "agentSession": {}}
            )
            is None
        )


@pytest.mark.unit
class TestHandleLinearEvent:
    @pytest.mark.asyncio
    async def test_dev_skip_verify_schedules_turn(self, monkeypatch):
        monkeypatch.setattr(lg, "_DEV_SKIP_VERIFY", True)
        monkeypatch.setattr(
            LinearGatewayUseCase, "_already_processed", AsyncMock(return_value=False)
        )
        bg = BackgroundTasks()
        out = await LinearGatewayUseCase().handle_linear_event(
            body=b"{}", headers={}, payload=_created_payload(), background=bg
        )
        assert out == {"ok": True}
        assert len(bg.tasks) == 1  # _run_turn scheduled

    @pytest.mark.asyncio
    async def test_bad_signature_is_dropped(self, monkeypatch):
        monkeypatch.setattr(lg, "_DEV_SKIP_VERIFY", False)
        monkeypatch.setattr(lg, "_WEBHOOK_SIGNING_SECRET", "shh")
        bg = BackgroundTasks()
        out = await LinearGatewayUseCase().handle_linear_event(
            body=b'{"x":1}',
            headers={"linear-signature": "deadbeef"},
            payload=_created_payload(),
            background=bg,
        )
        assert out == {"ok": False}
        assert len(bg.tasks) == 0

    @pytest.mark.asyncio
    async def test_duplicate_delivery_skipped(self, monkeypatch):
        monkeypatch.setattr(lg, "_DEV_SKIP_VERIFY", True)
        monkeypatch.setattr(
            LinearGatewayUseCase, "_already_processed", AsyncMock(return_value=True)
        )
        bg = BackgroundTasks()
        out = await LinearGatewayUseCase().handle_linear_event(
            body=b"{}",
            headers={"linear-delivery": "dup-1"},
            payload=_created_payload(),
            background=bg,
        )
        assert out == {"ok": True}
        assert len(bg.tasks) == 0  # not scheduled


@pytest.mark.unit
class TestActingIdentity:
    @pytest.mark.asyncio
    async def test_no_key_authz_off_is_dev_bypass(self, monkeypatch):
        monkeypatch.setattr(lg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.delenv("AGENTEX_AUTH_URL", raising=False)
        principal, headers = await LinearGatewayUseCase()._acting_identity()
        assert principal is None
        assert headers == {}

    @pytest.mark.asyncio
    async def test_no_key_authz_on_fails_closed(self, monkeypatch):
        monkeypatch.setattr(lg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setenv("AGENTEX_AUTH_URL", "http://auth")
        with pytest.raises(RuntimeError, match="refusing to dispatch"):
            await LinearGatewayUseCase()._acting_identity()

    @pytest.mark.asyncio
    async def test_sends_both_headers(self, monkeypatch):
        monkeypatch.setattr(lg, "_ACTING_BOT_API_KEY", "ssk_test")
        monkeypatch.setattr(lg, "_ACTING_ACCOUNT_ID", "acct_1")
        fake_authn = MagicMock()
        fake_authn.verify_headers = AsyncMock(
            return_value=SimpleNamespace(user_id="u1")
        )
        monkeypatch.setattr(
            "src.adapters.authentication.adapter_agentex_authn_proxy.AgentexAuthenticationProxy",
            MagicMock(return_value=fake_authn),
        )
        monkeypatch.setattr(
            "src.config.dependencies.resolve_environment_variable_dependency",
            lambda _key: "http://auth",
        )
        principal, headers = await LinearGatewayUseCase()._acting_identity()
        assert headers == {"x-api-key": "ssk_test", "x-selected-account-id": "acct_1"}
        assert principal.user_id == "u1"


def _fake_acp(existing_task=None, acp_type=None):
    """Fake ACP use case (mirrors the Slack test harness). existing_task=None → task
    doesn't exist (get_task raises → _dispatch will TASK_CREATE)."""
    acp = MagicMock()
    acp.agent_repository.get = AsyncMock(
        return_value=SimpleNamespace(id="agt_1", acp_type=acp_type or lg.ACPType.ASYNC)
    )
    created = SimpleNamespace(id="task_1", task_metadata=None)
    acp.handle_rpc_request = AsyncMock(return_value=created)
    acp.task_message_service.get_messages = AsyncMock(return_value=[])
    if existing_task is None:
        acp.task_service.get_task = AsyncMock(
            side_effect=lg.ItemDoesNotExist("no task")
        )
    else:
        acp.task_service.get_task = AsyncMock(return_value=existing_task)
    return acp, created


@pytest.mark.unit
class TestDispatch:
    @pytest.mark.asyncio
    async def test_new_session_creates_task_then_sends_event(self, monkeypatch):
        monkeypatch.setattr(lg, "_ACTING_BOT_API_KEY", "")  # -> (None, {})
        monkeypatch.setattr(lg, "GlobalDependencies", MagicMock())
        acp, _ = _fake_acp(existing_task=None)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            LinearGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )
        inbound = lg.InboundLinear(
            session_id="sess_1",
            actor="Someone",
            text="hello",
            selector=None,
            issue_id="iss_1",
            action="created",
        )
        await LinearGatewayUseCase()._dispatch(
            Target("golden-agent", config_id=lg._DEFAULT_CONFIG_ID),
            inbound,
            "hello",
            None,
            {},
        )
        assert acp.handle_rpc_request.await_count == 2
        first, second = acp.handle_rpc_request.await_args_list
        assert first.kwargs["method"] == AgentRPCMethod.TASK_CREATE
        assert first.kwargs["params"].name == "linear:sess_1"
        assert first.kwargs["params"].task_metadata["channel"] == "linear"
        assert first.kwargs["params"].params["config_id"] == lg._DEFAULT_CONFIG_ID
        assert second.kwargs["method"] == AgentRPCMethod.EVENT_SEND
        sent = second.kwargs["params"].content.content
        assert "hello" in sent and "issue_id=iss_1" in sent


class _FakeResp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = b"x"
        self.text = ""

    def json(self):
        return self._json


class _FakeClient:
    """Records POSTs and returns canned responses keyed on the URL suffix."""

    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        return self._handler(url, kw)


@pytest.mark.unit
class TestEmitAgentActivity:
    @pytest.mark.asyncio
    async def test_mints_token_then_posts_activity(self, monkeypatch):
        monkeypatch.setattr(lg, "_APP_TOKEN", {})
        monkeypatch.setattr(lg, "_CLIENT_ID", "cid")
        monkeypatch.setattr(lg, "_CLIENT_SECRET", "csecret")
        calls = []

        def handler(url, kw):
            calls.append(url)
            if url.endswith("/oauth/token"):
                return _FakeResp(200, {"access_token": "tok_123"})
            return _FakeResp(200, {"data": {"agentActivityCreate": {"success": True}}})

        monkeypatch.setattr(
            lg.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler)
        )
        inbound = lg.InboundLinear("sess_1", "", "hi", None, "iss_1", "created")
        await LinearGatewayUseCase()._emit(inbound, "response", "done")
        assert any(u.endswith("/oauth/token") for u in calls)
        assert any(u.endswith("/graphql") for u in calls)

    @pytest.mark.asyncio
    async def test_re_mints_on_401(self, monkeypatch):
        monkeypatch.setattr(lg, "_APP_TOKEN", {"token": "stale"})
        monkeypatch.setattr(lg, "_CLIENT_ID", "cid")
        monkeypatch.setattr(lg, "_CLIENT_SECRET", "csecret")
        graphql_calls = {"n": 0}
        minted = {"n": 0}

        def handler(url, kw):
            if url.endswith("/oauth/token"):
                minted["n"] += 1
                return _FakeResp(200, {"access_token": "fresh"})
            graphql_calls["n"] += 1
            # first graphql call 401 (stale token), second succeeds
            if graphql_calls["n"] == 1:
                return _FakeResp(401, {})
            return _FakeResp(200, {"data": {"agentActivityCreate": {"success": True}}})

        monkeypatch.setattr(
            lg.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler)
        )
        inbound = lg.InboundLinear("sess_1", "", "hi", None, "iss_1", "created")
        await LinearGatewayUseCase()._emit(inbound, "response", "done")
        assert graphql_calls["n"] == 2  # retried after 401
        assert minted["n"] == 1  # re-minted once

    @pytest.mark.asyncio
    async def test_no_client_creds_is_noop(self, monkeypatch):
        monkeypatch.setattr(lg, "_APP_TOKEN", {})
        monkeypatch.setattr(lg, "_CLIENT_ID", "")
        monkeypatch.setattr(lg, "_CLIENT_SECRET", "")
        called = {"n": 0}

        def handler(url, kw):
            called["n"] += 1
            return _FakeResp(200, {})

        monkeypatch.setattr(
            lg.httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler)
        )
        inbound = lg.InboundLinear("sess_1", "", "hi", None, "iss_1", "created")
        await LinearGatewayUseCase()._emit(inbound, "thought", "on it")
        assert called["n"] == 0  # no token → no HTTP call
