"""Unit tests for the Slack gateway — everything that does NOT require a real Slack
app: signature verification, event normalization, the handle_slack_event control flow
(challenge / dev-skip / drop / ack), and that _run_turn dispatches correctly (ACP
mocked). No running stack, no golden_agent, no Slack.
"""

import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks
from src.domain.entities.agents_rpc import AgentRPCMethod
from src.domain.use_cases import slack_gateway_use_case as sg
from src.domain.use_cases.slack_gateway_use_case import (
    SlackGatewayUseCase,
    Target,
    normalize,
    verify_signature,
)


def _sign(secret: str, ts: str, body: bytes) -> str:
    basis = b"v0:" + ts.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), basis, hashlib.sha256).hexdigest()


# Captured before the autouse fixture patches the class, so the repo-lookup tests can
# exercise the real implementation.
_REAL_GET_AGENT_BY_NAME = SlackGatewayUseCase._get_agent_by_name


@pytest.fixture(autouse=True)
def _no_runtime_agents(monkeypatch):
    """Default: no selector names a registered agent, so resolution falls to
    golden_agent (no DB hit). Tests that exercise non-golden routing override this."""
    monkeypatch.setattr(
        SlackGatewayUseCase, "_get_agent_by_name", AsyncMock(return_value=None)
    )


@pytest.mark.unit
class TestVerifySignature:
    def test_valid_signature_passes(self):
        secret, ts, body = "shh", str(int(time.time())), b'{"x":1}'
        assert verify_signature(secret, ts, _sign(secret, ts, body), body) is True

    def test_wrong_signature_fails(self):
        ts, body = str(int(time.time())), b'{"x":1}'
        assert verify_signature("shh", ts, _sign("other", ts, body), body) is False

    def test_stale_timestamp_fails(self):
        secret, body = "shh", b'{"x":1}'
        ts = str(int(time.time()) - 60 * 10)  # 10 min old > 5 min guard
        assert verify_signature(secret, ts, _sign(secret, ts, body), body) is False

    def test_nonnumeric_timestamp_fails(self):
        assert verify_signature("shh", "not-a-number", "v0=whatever", b"{}") is False


@pytest.mark.unit
class TestNormalize:
    def test_app_mention_strips_mention_and_extracts_fields(self):
        payload = {
            "team_id": "T1",
            "event": {
                "type": "app_mention",
                "user": "U1",
                "text": "<@UBOT> pr-bot do the thing",
                "channel": "C1",
                "ts": "1700000000.000100",
            },
        }
        inbound = normalize(payload)
        assert inbound is not None
        assert inbound.team_id == "T1"
        assert inbound.channel == "C1"
        assert inbound.user == "U1"
        assert inbound.text == "pr-bot do the thing"
        assert inbound.selector == "pr-bot"
        assert inbound.thread_ts == "1700000000.000100"  # falls back to ts

    def test_message_uses_thread_ts_when_present(self):
        payload = {
            "event": {
                "type": "message",
                "user": "U1",
                "text": "follow up",
                "channel": "C1",
                "ts": "1700000000.000200",
                "thread_ts": "1700000000.000100",
            }
        }
        inbound = normalize(payload)
        assert inbound is not None
        assert inbound.thread_ts == "1700000000.000100"
        assert inbound.selector == "follow"

    def test_ignores_bot_and_subtype_and_other_types(self):
        assert (
            normalize({"event": {"type": "app_mention", "bot_id": "B1", "text": "x"}})
            is None
        )
        assert (
            normalize(
                {
                    "event": {
                        "type": "message",
                        "subtype": "message_changed",
                        "text": "x",
                    }
                }
            )
            is None
        )
        assert normalize({"event": {"type": "reaction_added"}}) is None

    def test_empty_text_gives_no_selector(self):
        inbound = normalize(
            {
                "event": {
                    "type": "app_mention",
                    "text": "<@UBOT>",
                    "channel": "C1",
                    "ts": "1",
                }
            }
        )
        assert inbound is not None
        assert inbound.selector is None


@pytest.mark.unit
class TestHandleSlackEvent:
    @pytest.mark.asyncio
    async def test_url_verification_returns_challenge_without_dispatch(self):
        bg = BackgroundTasks()
        result = await SlackGatewayUseCase().handle_slack_event(
            body=b"{}",
            headers={},
            payload={"type": "url_verification", "challenge": "abc"},
            background=bg,
        )
        assert result == {"challenge": "abc"}
        assert len(bg.tasks) == 0

    @pytest.mark.asyncio
    async def test_dev_skip_verify_schedules_turn(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        bg = BackgroundTasks()
        payload = {
            "event": {
                "type": "app_mention",
                "text": "<@UBOT> hi",
                "channel": "C1",
                "ts": "1",
            }
        }
        result = await SlackGatewayUseCase().handle_slack_event(
            body=b"{}", headers={}, payload=payload, background=bg
        )
        assert result == {"ok": True}
        assert len(bg.tasks) == 1  # _run_turn scheduled

    @pytest.mark.asyncio
    async def test_bad_signature_drops_without_dispatch(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", False)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_fetch_signing_secret", AsyncMock(return_value="shh"))
        bg = BackgroundTasks()
        result = await uc.handle_slack_event(
            body=b"{}",
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "v0=bad",
            },
            payload={
                "api_app_id": "A1",
                "event": {"type": "app_mention", "text": "<@U> hi"},
            },
            background=bg,
        )
        assert result == {"ok": False}
        assert len(bg.tasks) == 0

    @pytest.mark.asyncio
    async def test_valid_signature_schedules_turn(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", False)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_fetch_signing_secret", AsyncMock(return_value="shh"))
        ts, body = str(int(time.time())), b'{"api_app_id":"A1"}'
        headers = {
            "x-slack-request-timestamp": ts,
            "x-slack-signature": _sign("shh", ts, body),
        }
        payload = {
            "api_app_id": "A1",
            "event": {
                "type": "app_mention",
                "text": "<@U> hi",
                "channel": "C1",
                "ts": "1",
            },
        }
        bg = BackgroundTasks()
        result = await uc.handle_slack_event(
            body=body, headers=headers, payload=payload, background=bg
        )
        assert result == {"ok": True}
        assert len(bg.tasks) == 1


@pytest.mark.unit
class TestTurnContent:
    def test_prepends_channel_context_and_preserves_prompt(self):
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C123",
            user="U",
            text="summarize",
            thread_ts="1700.1",
            selector=None,
        )
        content = sg._turn_content(inbound, "summarize")
        assert "channel_id=C123" in content
        assert "thread_ts=1700.1" in content
        assert content.endswith("summarize")  # user's prompt after the context block


@pytest.mark.unit
class TestResolveTarget:
    @pytest.mark.asyncio
    async def test_defaults_to_golden_agent_with_full_text(self):
        uc = SlackGatewayUseCase()
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C",
            user="U",
            text="pr-bot do it",
            thread_ts="1",
            selector="pr-bot",
        )
        target, prompt = await uc._resolve_target("acct", inbound)
        assert target == Target(agent_name="golden-agent", config_id=None)
        assert prompt == "pr-bot do it"  # no stripping in the default branch

    @pytest.mark.asyncio
    async def test_selector_matching_registered_agent_routes_to_it(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc,
            "_get_agent_by_name",
            AsyncMock(return_value=SimpleNamespace(id="a1", name="pr-bot")),
        )
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C",
            user="U",
            text="pr-bot do it",
            thread_ts="1",
            selector="pr-bot",
        )
        target, prompt = await uc._resolve_target("acct", inbound)
        assert target == Target(agent_name="pr-bot", config_id=None)  # NOT golden_agent
        assert prompt == "do it"  # selector stripped once it matched


def _fake_acp(existing_task=None):
    """Fake ACP use case. existing_task=None → task doesn't exist yet (get_task raises,
    so _dispatch will TASK_CREATE); pass a task to simulate a resumed thread."""
    acp = MagicMock()
    acp.agent_repository.get = AsyncMock(return_value=SimpleNamespace(id="agt_1"))
    created = SimpleNamespace(id="task_1", task_metadata=None)
    acp.handle_rpc_request = AsyncMock(return_value=created)
    acp.task_message_service.get_messages = AsyncMock(
        return_value=[]
    )  # reply-poll snapshot
    if existing_task is None:
        acp.task_service.get_task = AsyncMock(
            side_effect=sg.ItemDoesNotExist("no task")
        )
    else:
        acp.task_service.get_task = AsyncMock(return_value=existing_task)
    return acp, created


@pytest.mark.unit
class TestDispatch:
    @pytest.mark.asyncio
    async def test_new_thread_creates_task_then_sends_event(self, monkeypatch):
        monkeypatch.setattr(
            sg, "_ACTING_USER_API_KEY", ""
        )  # -> (None, {}), no authn proxy
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        acp, _ = _fake_acp(existing_task=None)  # new thread → create
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )

        inbound = sg.InboundSlack(
            team_id="T",
            channel="C1",
            user="U",
            text="hello",
            thread_ts="1700000000.000100",
            selector=None,
        )
        await SlackGatewayUseCase()._dispatch(Target("golden-agent"), inbound, "hello")

        assert acp.handle_rpc_request.await_count == 2
        first, second = acp.handle_rpc_request.await_args_list
        assert first.kwargs["method"] == AgentRPCMethod.TASK_CREATE
        assert first.kwargs["params"].name == "slack:1700000000.000100"
        assert second.kwargs["method"] == AgentRPCMethod.EVENT_SEND
        # The turn content carries the user's prompt plus the Slack channel context so
        # the agent can point its Slack tools at the right conversation.
        sent = second.kwargs["params"].content.content
        assert "hello" in sent
        assert "channel_id=C1" in sent

    @pytest.mark.asyncio
    async def test_existing_thread_skips_create_but_sends_event(self, monkeypatch):
        # Same-thread follow-up: the task/workflow already exists, so we must NOT
        # TASK_CREATE (it would re-start the running workflow) — only EVENT_SEND.
        monkeypatch.setattr(sg, "_ACTING_USER_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        existing = SimpleNamespace(id="task_1", task_metadata=None)
        acp, _ = _fake_acp(existing_task=existing)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )

        inbound = sg.InboundSlack(
            team_id="T", channel="C1", user="U", text="hi", thread_ts="1", selector=None
        )
        await SlackGatewayUseCase()._dispatch(Target("golden-agent"), inbound, "hi")

        assert acp.handle_rpc_request.await_count == 1
        assert (
            acp.handle_rpc_request.await_args.kwargs["method"]
            == AgentRPCMethod.EVENT_SEND
        )

    @pytest.mark.asyncio
    async def test_concurrent_first_turn_falls_back_to_existing_task(self, monkeypatch):
        # Two first events for the same thread race: this one loses the create (the
        # globally-unique task name is already taken), so TASK_CREATE raises
        # DuplicateItemError. It must fall back to the task the winner created and
        # still send its own event rather than dropping the turn.
        monkeypatch.setattr(sg, "_ACTING_USER_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        winner_task = SimpleNamespace(id="task_1", task_metadata=None)
        acp = MagicMock()
        acp.agent_repository.get = AsyncMock(return_value=SimpleNamespace(id="agt_1"))
        acp.task_message_service.get_messages = AsyncMock(return_value=[])
        # 1st get_task = existence probe (absent); 2nd = post-race fallback (winner).
        acp.task_service.get_task = AsyncMock(
            side_effect=[sg.ItemDoesNotExist("no task"), winner_task]
        )

        async def rpc(*, method, **_):
            if method == AgentRPCMethod.TASK_CREATE:
                raise sg.DuplicateItemError("name taken")
            return None  # EVENT_SEND

        acp.handle_rpc_request = AsyncMock(side_effect=rpc)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )

        inbound = sg.InboundSlack(
            team_id="T", channel="C1", user="U", text="hi", thread_ts="1", selector=None
        )
        await SlackGatewayUseCase()._dispatch(Target("golden-agent"), inbound, "hi")

        # Create was attempted and raced, then the event still went out against the
        # winner's task (re-fetched by name).
        methods = [c.kwargs["method"] for c in acp.handle_rpc_request.await_args_list]
        assert methods == [AgentRPCMethod.TASK_CREATE, AgentRPCMethod.EVENT_SEND]
        assert acp.task_service.get_task.await_count == 2


@pytest.mark.unit
class TestRunTurn:
    @pytest.mark.asyncio
    async def test_delivers_reply_with_attribution(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_dispatch", AsyncMock(return_value="the answer"))
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_deliver", deliver)
        inbound = sg.InboundSlack(
            team_id="T", channel="C", user="U", text="hi", thread_ts="1", selector="hi"
        )

        await uc._run_turn(inbound)

        text = deliver.await_args.args[1]
        assert "the answer" in text
        assert "via golden-agent" in text

    @pytest.mark.asyncio
    async def test_denied_authz_does_not_dispatch(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_authorize", AsyncMock(return_value=False))
        dispatch = AsyncMock()
        monkeypatch.setattr(uc, "_dispatch", dispatch)
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_deliver", deliver)
        inbound = sg.InboundSlack(
            team_id="T", channel="C", user="U", text="hi", thread_ts="1", selector="hi"
        )

        await uc._run_turn(inbound)

        dispatch.assert_not_awaited()
        assert "not authorized" in deliver.await_args.args[1].lower()


@pytest.mark.unit
class TestTwoEventsEndToEnd:
    """The two turn-driving events, end to end: payload -> handle_slack_event ->
    scheduled _run_turn -> _dispatch, asserting the right thread + prompt reach dispatch."""

    _APP_MENTION = {
        "team_id": "T1",
        "event": {
            "type": "app_mention",
            "user": "U1",
            "text": "<@UBOT> summarize this",
            "channel": "C1",
            "ts": "1700000000.000100",
        },
    }
    _MESSAGE_IM = {
        "team_id": "T1",
        "event": {
            "type": "message",
            "channel_type": "im",
            "user": "U1",
            "text": "and the next step?",
            "channel": "D1",
            "ts": "1700000000.000200",
            "thread_ts": "1700000000.000100",
        },
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload, expected_thread, expected_prompt",
        [
            (_APP_MENTION, "1700000000.000100", "summarize this"),
            (_MESSAGE_IM, "1700000000.000100", "and the next step?"),
        ],
    )
    async def test_event_drives_dispatch(
        self, monkeypatch, payload, expected_thread, expected_prompt
    ):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        dispatch = AsyncMock(return_value="answer")
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_dispatch", dispatch)
        monkeypatch.setattr(uc, "_deliver", deliver)

        bg = BackgroundTasks()
        result = await uc.handle_slack_event(
            body=b"{}", headers={}, payload=payload, background=bg
        )

        assert result == {"ok": True}
        assert len(bg.tasks) == 1  # a turn was scheduled

        # Run the scheduled background turn.
        task = bg.tasks[0]
        await task.func(*task.args, **task.kwargs)

        dispatch.assert_awaited_once()
        target, inbound_arg, prompt = dispatch.await_args.args
        assert target.agent_name == "golden-agent"
        assert inbound_arg.thread_ts == expected_thread
        assert prompt == expected_prompt
        deliver.assert_awaited_once()


@pytest.mark.unit
class TestNonGoldenAgent:
    @pytest.mark.asyncio
    async def test_event_routes_to_non_golden_runtime_end_to_end(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        # pr-bot is a registered agent; golden_agent is not what should run here.
        monkeypatch.setattr(
            uc,
            "_get_agent_by_name",
            AsyncMock(return_value=SimpleNamespace(id="a1", name="pr-bot")),
        )
        dispatch = AsyncMock(return_value="done")
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_dispatch", dispatch)
        monkeypatch.setattr(uc, "_deliver", deliver)

        payload = {
            "team_id": "T1",
            "event": {
                "type": "app_mention",
                "user": "U1",
                "text": "<@UBOT> pr-bot review PR 42",
                "channel": "C1",
                "ts": "1700000000.000100",
            },
        }
        bg = BackgroundTasks()
        await uc.handle_slack_event(
            body=b"{}", headers={}, payload=payload, background=bg
        )
        await bg.tasks[0].func(*bg.tasks[0].args)

        target, inbound_arg, prompt = dispatch.await_args.args
        assert target.agent_name == "pr-bot"  # routed to the non-golden runtime
        assert prompt == "review PR 42"  # selector stripped
        assert "via pr-bot" in deliver.await_args.args[1]

    @pytest.mark.asyncio
    async def test_dispatch_looks_up_the_target_agent_by_name(self, monkeypatch):
        monkeypatch.setattr(sg, "_ACTING_USER_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        acp, _ = _fake_acp(existing_task=None)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )

        inbound = sg.InboundSlack(
            team_id="T", channel="C1", user="U", text="hi", thread_ts="1", selector=None
        )
        await SlackGatewayUseCase()._dispatch(Target("pr-bot"), inbound, "hi")

        # dispatch is agent-agnostic — it resolves whatever target it's given.
        acp.agent_repository.get.assert_awaited_once_with(name="pr-bot")


@pytest.mark.unit
class TestCollectReply:
    @pytest.mark.asyncio
    async def test_returns_settled_agent_text(self):
        msg = SimpleNamespace(
            id="m1",
            content=SimpleNamespace(
                author=sg.MessageAuthor.AGENT, content="the answer"
            ),
        )
        svc = SimpleNamespace(get_messages=AsyncMock(return_value=[msg]))
        reply = await SlackGatewayUseCase()._collect_reply(
            svc, "task_1", seen=set(), interval_s=0.01, quiescence_s=0.0, timeout_s=1.0
        )
        assert reply == "the answer"

    @pytest.mark.asyncio
    async def test_ignores_messages_seen_before_the_turn(self):
        old = SimpleNamespace(
            id="m0",
            content=SimpleNamespace(author=sg.MessageAuthor.AGENT, content="old"),
        )
        svc = SimpleNamespace(get_messages=AsyncMock(return_value=[old]))
        reply = await SlackGatewayUseCase()._collect_reply(
            svc,
            "task_1",
            seen={"m0"},
            interval_s=0.01,
            quiescence_s=0.0,
            timeout_s=0.05,
        )
        assert reply is None  # only pre-existing messages → nothing new

    @pytest.mark.asyncio
    async def test_polls_newest_first_and_returns_chronological_text(self):
        # get_messages is fetched DESC (newest-first) so this turn's reply is in the
        # window even once the task has more than _MESSAGE_PAGE messages; the page is
        # then reversed to chronological before a multi-part reply is joined.
        m2 = SimpleNamespace(
            id="m2",
            content=SimpleNamespace(author=sg.MessageAuthor.AGENT, content="second"),
        )
        m1 = SimpleNamespace(
            id="m1",
            content=SimpleNamespace(author=sg.MessageAuthor.AGENT, content="first"),
        )
        get_messages = AsyncMock(return_value=[m2, m1])  # newest-first
        svc = SimpleNamespace(get_messages=get_messages)
        reply = await SlackGatewayUseCase()._collect_reply(
            svc, "task_1", seen=set(), interval_s=0.01, quiescence_s=0.0, timeout_s=1.0
        )
        assert reply == "first\n\nsecond"  # chronological order restored
        assert get_messages.await_args.kwargs["order_direction"] == "desc"


@pytest.mark.unit
class TestDeliver:
    @pytest.mark.asyncio
    async def test_posts_to_thread_with_bot_token(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        captured = {}

        class _Resp:
            def json(self):
                return {"ok": True}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

            async def post(self, url, headers=None, json=None):
                captured.update(url=url, headers=headers, json=json)
                return _Resp()

        monkeypatch.setattr(sg.httpx, "AsyncClient", lambda *a, **k: _Client())
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C1",
            user="U",
            text="x",
            thread_ts="1700.1",
            selector=None,
        )

        await SlackGatewayUseCase()._deliver(inbound, "the answer")

        assert captured["url"].endswith("/chat.postMessage")
        assert captured["headers"]["Authorization"] == "Bearer xoxb-test"
        assert captured["json"] == {
            "channel": "C1",
            "thread_ts": "1700.1",
            "text": "the answer",
        }

    @pytest.mark.asyncio
    async def test_no_token_skips_without_error(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        inbound = sg.InboundSlack(
            team_id="T", channel="C", user="U", text="x", thread_ts="1", selector=None
        )
        await SlackGatewayUseCase()._deliver(
            inbound, "hi"
        )  # logs + returns, no HTTP call


@pytest.mark.unit
class TestGatewaySecrets:
    """The throwaway DB store: bot token / signing secret read from agent_api_keys
    (via _gateway_secret), env fallback, and fail-safe when there's no DB."""

    @pytest.mark.asyncio
    async def test_bot_token_from_db(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc, "_gateway_secret", AsyncMock(return_value="xoxb-from-db")
        )
        assert await uc._fetch_bot_token() == "xoxb-from-db"
        uc._gateway_secret.assert_awaited_once_with("slack-bot-token")

    @pytest.mark.asyncio
    async def test_bot_token_env_fallback(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env")
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_gateway_secret", AsyncMock(return_value=""))
        assert await uc._fetch_bot_token() == "xoxb-env"

    @pytest.mark.asyncio
    async def test_signing_secret_from_db(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_gateway_secret", AsyncMock(return_value="sign-db"))
        assert await uc._fetch_signing_secret("A123") == "sign-db"
        uc._gateway_secret.assert_awaited_once_with("slack-signing-secret")

    @pytest.mark.asyncio
    async def test_gateway_secret_fail_safe_without_db(self, monkeypatch):
        # No engine / GlobalDependencies in a unit test → fail-safe to "".
        monkeypatch.setattr(
            sg,
            "database_async_read_write_engine",
            MagicMock(side_effect=RuntimeError("no db")),
        )
        assert await SlackGatewayUseCase()._gateway_secret("A123:bot") == ""


def _patch_authn(monkeypatch, user_id="u1"):
    fake_authn = MagicMock()
    fake_authn.verify_headers = AsyncMock(return_value=SimpleNamespace(user_id=user_id))
    monkeypatch.setattr(
        "src.adapters.authentication.adapter_agentex_authn_proxy.AgentexAuthenticationProxy",
        MagicMock(return_value=fake_authn),
    )
    monkeypatch.setattr(
        "src.config.dependencies.resolve_environment_variable_dependency",
        lambda _key: "http://auth",
    )
    return fake_authn


@pytest.mark.unit
class TestActingIdentity:
    @pytest.mark.asyncio
    async def test_no_key_is_dev_bypass(self, monkeypatch):
        monkeypatch.setattr(sg, "_ACTING_USER_API_KEY", "")
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc, "_gateway_secret", AsyncMock(return_value="")
        )  # no DB value
        principal, headers = await uc._acting_identity()
        assert principal is None
        assert headers == {}

    @pytest.mark.asyncio
    async def test_env_fallback_sends_both_headers(self, monkeypatch):
        # DB empty → fall back to env; auth needs x-api-key AND x-selected-account-id.
        monkeypatch.setattr(sg, "_ACTING_USER_API_KEY", "ssk_test")
        monkeypatch.setattr(sg, "_ACTING_ACCOUNT_ID", "acct_1")
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_gateway_secret", AsyncMock(return_value=""))
        fake_authn = _patch_authn(monkeypatch)

        principal, headers = await uc._acting_identity()

        assert headers == {"x-api-key": "ssk_test", "x-selected-account-id": "acct_1"}
        fake_authn.verify_headers.assert_awaited_once_with(headers)
        assert principal.user_id == "u1"

    @pytest.mark.asyncio
    async def test_db_takes_precedence_over_env(self, monkeypatch):
        # DB values (slack-acting-user-api-key / slack-acting-account-id) win over env.
        monkeypatch.setattr(sg, "_ACTING_USER_API_KEY", "env-key")
        monkeypatch.setattr(sg, "_ACTING_ACCOUNT_ID", "env-acct")
        uc = SlackGatewayUseCase()

        async def fake_secret(name):
            return {
                "slack-acting-user-api-key": "db-key",
                "slack-acting-account-id": "db-acct",
            }.get(name, "")

        monkeypatch.setattr(uc, "_gateway_secret", AsyncMock(side_effect=fake_secret))
        _patch_authn(monkeypatch)

        _, headers = await uc._acting_identity()

        assert headers == {"x-api-key": "db-key", "x-selected-account-id": "db-acct"}


@pytest.mark.unit
class TestGetAgentByNameRepo:
    """The runtime-registry lookup is a credential-free repo read — no API key."""

    @staticmethod
    def _patch_db(monkeypatch, fake_repo):
        monkeypatch.setattr(sg, "database_async_read_write_engine", lambda: object())
        monkeypatch.setattr(
            sg, "database_async_read_write_session_maker", lambda _e: object()
        )
        monkeypatch.setattr(
            sg, "database_async_read_only_session_maker", lambda _e: object()
        )
        monkeypatch.setattr(sg, "AgentRepository", MagicMock(return_value=fake_repo))

    @pytest.mark.asyncio
    async def test_found_returns_agent(self, monkeypatch):
        fake_repo = MagicMock()
        fake_repo.get = AsyncMock(return_value=SimpleNamespace(id="a1", name="pr-bot"))
        self._patch_db(monkeypatch, fake_repo)

        result = await _REAL_GET_AGENT_BY_NAME(SlackGatewayUseCase(), "pr-bot")

        assert result.name == "pr-bot"
        fake_repo.get.assert_awaited_once_with(name="pr-bot")

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, monkeypatch):
        fake_repo = MagicMock()
        fake_repo.get = AsyncMock(side_effect=sg.ItemDoesNotExist("nope"))
        self._patch_db(monkeypatch, fake_repo)

        result = await _REAL_GET_AGENT_BY_NAME(SlackGatewayUseCase(), "nope")

        assert result is None


@pytest.mark.unit
class TestAgentsListResponse:
    def test_formats_agents_ephemerally(self):
        agents = [
            SimpleNamespace(name="pr-bot", description="Reviews PRs"),
            SimpleNamespace(name="golden-agent", description="General assistant"),
        ]
        resp = sg._agents_list_response(agents)
        assert resp["response_type"] == "ephemeral"
        assert "@agent pr-bot" in resp["text"]
        assert "Reviews PRs" in resp["text"]
        assert "golden-agent" in resp["text"]

    def test_empty_list_message(self):
        resp = sg._agents_list_response([])
        assert resp["response_type"] == "ephemeral"
        assert "No agents" in resp["text"]


@pytest.mark.unit
class TestListAgents:
    @staticmethod
    def _patch_db(monkeypatch, fake_repo):
        monkeypatch.setattr(sg, "database_async_read_write_engine", lambda: object())
        monkeypatch.setattr(
            sg, "database_async_read_write_session_maker", lambda _e: object()
        )
        monkeypatch.setattr(
            sg, "database_async_read_only_session_maker", lambda _e: object()
        )
        monkeypatch.setattr(sg, "AgentRepository", MagicMock(return_value=fake_repo))

    @pytest.mark.asyncio
    async def test_returns_ready_agents_sorted(self, monkeypatch):
        fake_repo = MagicMock()
        fake_repo.list = AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="zeta", status=sg.AgentStatus.READY, description="z"
                ),
                SimpleNamespace(
                    name="alpha", status=sg.AgentStatus.READY, description="a"
                ),
                SimpleNamespace(
                    name="not-ready", status=sg.AgentStatus.BUILD_ONLY, description="b"
                ),
            ]
        )
        self._patch_db(monkeypatch, fake_repo)

        agents = await SlackGatewayUseCase()._list_agents()

        assert [a.name for a in agents] == ["alpha", "zeta"]  # ready-only, name-sorted


@pytest.mark.unit
class TestHandleSlashCommand:
    @pytest.mark.asyncio
    async def test_agents_command_lists_agents(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc,
            "_list_agents",
            AsyncMock(
                return_value=[SimpleNamespace(name="pr-bot", description="Reviews PRs")]
            ),
        )
        resp = await uc.handle_slash_command(
            body=b"", headers={}, form={"command": "/agents"}
        )
        assert resp["response_type"] == "ephemeral"
        assert "pr-bot" in resp["text"]

    @pytest.mark.asyncio
    async def test_unknown_command_is_reported(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        resp = await SlackGatewayUseCase().handle_slash_command(
            body=b"", headers={}, form={"command": "/whoami"}
        )
        assert "Unsupported command" in resp["text"]

    @pytest.mark.asyncio
    async def test_bad_signature_rejected(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", False)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_fetch_signing_secret", AsyncMock(return_value="shh"))
        resp = await uc.handle_slash_command(
            body=b"cmd=/agents",
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "v0=bad",
            },
            form={"command": "/agents", "api_app_id": "A1"},
        )
        assert "Signature verification failed" in resp["text"]
