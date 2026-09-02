"""Unit tests for the Slack gateway — everything that does NOT require a real Slack
app: signature verification, event normalization, the handle_slack_event control flow
(challenge / dev-skip / drop / ack), and that _run_turn dispatches correctly (ACP
mocked). No running stack, no golden_agent, no Slack.
"""

import contextlib
import hashlib
import hmac
import json
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


def _inbound(**kw) -> sg.InboundSlack:
    """InboundSlack with defaults, so a test states only what it cares about."""
    return sg.InboundSlack(
        **{
            "team_id": "T1",
            "channel": "C1",
            "user": "U1",
            "text": "hi",
            "thread_ts": "1",
            "selector": None,
            **kw,
        }
    )


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


@pytest.fixture(autouse=True)
def _unlinked_by_default(monkeypatch):
    """Default: the invoking Slack user has no identity link (no DB hit), and an
    unlinked user falls back to the shared bot — i.e. pre-user-scoping behavior, which
    is what the existing tests assert. Tests for the linked path override this."""
    monkeypatch.setattr(
        SlackGatewayUseCase, "_resolve_invoking_identity", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", False)


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
class TestEventDedup:
    """Slack's HTTP Events API is at-least-once; a retried event_id must not start a
    second turn. Dedup fail-open so it can never drop a legitimate first delivery."""

    _PAYLOAD = {
        "event": {"type": "app_mention", "text": "<@U> hi", "channel": "C1", "ts": "1"},
        "event_id": "Ev1",
    }

    @pytest.mark.asyncio
    async def test_duplicate_event_is_not_dispatched(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_already_processed", AsyncMock(return_value=True))
        bg = BackgroundTasks()
        result = await uc.handle_slack_event(
            body=b"{}", headers={}, payload=self._PAYLOAD, background=bg
        )
        assert result == {"ok": True}
        assert len(bg.tasks) == 0  # deduped -> no turn scheduled

    @pytest.mark.asyncio
    async def test_first_delivery_is_dispatched(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        seen = AsyncMock(return_value=False)
        monkeypatch.setattr(uc, "_already_processed", seen)
        bg = BackgroundTasks()
        await uc.handle_slack_event(
            body=b"{}", headers={}, payload=self._PAYLOAD, background=bg
        )
        assert len(bg.tasks) == 1
        seen.assert_awaited_once_with("Ev1")  # deduped on the envelope event_id

    @pytest.mark.asyncio
    async def test_already_processed_fail_open_without_redis(self, monkeypatch):
        # No Redis pool (deps not up) -> fail-open (False) so the turn still runs.
        monkeypatch.setattr(
            sg,
            "GlobalDependencies",
            MagicMock(return_value=SimpleNamespace(redis_pool=None)),
        )
        assert await SlackGatewayUseCase()._already_processed("Ev1") is False

    @pytest.mark.asyncio
    async def test_already_processed_no_event_id_is_false(self):
        uc = SlackGatewayUseCase()
        assert await uc._already_processed(None) is False
        assert await uc._already_processed("") is False


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
        assert "post_message" not in content  # read-only context by default

    def test_self_posts_adds_post_directive(self):
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C123",
            user="U",
            text="summarize",
            thread_ts="1700.1",
            selector=None,
        )
        content = sg._turn_content(inbound, "summarize", self_posts=True)
        # golden-agent is told to deliver its own reply into the thread, and to keep the
        # thinking indicator alive across multi-message turns via set_status.
        assert "post_message" in content
        assert "set_status" in content
        assert "channel_id=C123" in content and "thread_ts=1700.1" in content
        assert content.endswith("summarize")


@pytest.mark.unit
class TestResolveTarget:
    @pytest.mark.asyncio
    async def test_unmatched_selector_falls_back_to_default_config(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEFAULT_CONFIG_ID", "pinned-default")
        # selector names no SGP config and no registered agent -> golden-agent + the
        # default config id; the whole message stays the prompt (nothing stripped).
        uc = SlackGatewayUseCase()
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C",
            user="U",
            text="pr-bot do it",
            thread_ts="1",
            selector="pr-bot",
        )
        target, prompt = await uc._resolve_target(inbound, {})
        assert target == Target("golden-agent", config_id="pinned-default")
        assert prompt == "pr-bot do it"

    @pytest.mark.asyncio
    async def test_selector_matching_sgp_config_runs_golden_with_that_config(
        self, monkeypatch
    ):
        # selector resolves to an SGP agent_config -> golden-agent + that config_id.
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_resolve_config_id", AsyncMock(return_value="cfg-9"))
        inbound = sg.InboundSlack(
            team_id="T",
            channel="C",
            user="U",
            text="pr-bot do it",
            thread_ts="1",
            selector="pr-bot",
        )
        target, prompt = await uc._resolve_target(inbound, {"x-api-key": "k"})
        assert target == Target("golden-agent", config_id="cfg-9")
        assert prompt == "do it"  # selector stripped once it matched a config

    @pytest.mark.asyncio
    async def test_selector_matching_registered_agent_routes_to_it(self, monkeypatch):
        # No SGP config by that name, but a registered runtime exists -> route to it.
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_resolve_config_id", AsyncMock(return_value=None))
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
        target, prompt = await uc._resolve_target(inbound, {"x-api-key": "k"})
        assert target == Target(agent_name="pr-bot", config_id=None)  # NOT golden
        assert prompt == "do it"  # selector stripped


def _fake_acp(existing_task=None, acp_type=None):
    """Fake ACP use case. existing_task=None → task doesn't exist yet (get_task raises,
    so _dispatch will TASK_CREATE); pass a task to simulate a resumed thread. acp_type
    defaults to ASYNC (the golden-agent path); pass ACPType.SYNC for the message/send
    path."""
    acp = MagicMock()
    acp.agent_repository.get = AsyncMock(
        return_value=SimpleNamespace(id="agt_1", acp_type=acp_type or sg.ACPType.ASYNC)
    )
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
            sg, "_ACTING_BOT_API_KEY", ""
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
        await SlackGatewayUseCase()._dispatch(
            Target("golden-agent", config_id="cfg-1"),
            inbound,
            "hello",
            None,
            {},
        )

        assert acp.handle_rpc_request.await_count == 2
        first, second = acp.handle_rpc_request.await_args_list
        assert first.kwargs["method"] == AgentRPCMethod.TASK_CREATE
        assert first.kwargs["params"].name == "slack:1700000000.000100"
        # First turn passes the resolved agent_config id so golden-agent resolves its
        # full turn config (prompt/model/tools) from it.
        assert first.kwargs["params"].params["config_id"] == "cfg-1"
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
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
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
        await SlackGatewayUseCase()._dispatch(
            Target("golden-agent"), inbound, "hi", None, {}
        )

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
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        winner_task = SimpleNamespace(id="task_1", task_metadata=None)
        acp = MagicMock()
        acp.agent_repository.get = AsyncMock(
            return_value=SimpleNamespace(id="agt_1", acp_type=sg.ACPType.ASYNC)
        )
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
        await SlackGatewayUseCase()._dispatch(
            Target("golden-agent"), inbound, "hi", None, {}
        )

        # Create was attempted and raced, then the event still went out against the
        # winner's task (re-fetched by name).
        methods = [c.kwargs["method"] for c in acp.handle_rpc_request.await_args_list]
        assert methods == [AgentRPCMethod.TASK_CREATE, AgentRPCMethod.EVENT_SEND]
        assert acp.task_service.get_task.await_count == 2

    @pytest.mark.asyncio
    async def test_async_create_race_retries_lookup_through_replica_lag(
        self, monkeypatch
    ):
        # After the create-race, the fallback get_task reads the replica — which may lag
        # and miss the winner's task. Retry until it catches up rather than dropping the
        # turn with ItemDoesNotExist.
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        monkeypatch.setattr(sg, "_CREATE_RACE_BACKOFF_S", 0.0)
        winner_task = SimpleNamespace(id="task_1", task_metadata=None)
        acp = MagicMock()
        acp.agent_repository.get = AsyncMock(
            return_value=SimpleNamespace(id="agt_1", acp_type=sg.ACPType.ASYNC)
        )
        acp.task_message_service.get_messages = AsyncMock(return_value=[])
        # probe (absent) → resolve miss (replica lag) → resolve hit (winner).
        acp.task_service.get_task = AsyncMock(
            side_effect=[
                sg.ItemDoesNotExist("no task"),
                sg.ItemDoesNotExist("replica lag"),
                winner_task,
            ]
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
        await SlackGatewayUseCase()._dispatch(
            Target("golden-agent"), inbound, "hi", None, {}
        )

        assert acp.task_service.get_task.await_count == 3  # probe + miss + hit
        methods = [c.kwargs["method"] for c in acp.handle_rpc_request.await_args_list]
        assert methods == [AgentRPCMethod.TASK_CREATE, AgentRPCMethod.EVENT_SEND]

    @pytest.mark.asyncio
    async def test_sync_agent_uses_message_send_and_returns_reply(self, monkeypatch):
        # A SYNC agent has no event stream: dispatch does ONE message/send (get-or-create
        # + reply), not task/create + event/send + poll.
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        acp, _ = _fake_acp(acp_type=sg.ACPType.SYNC)
        reply_msg = SimpleNamespace(
            content=SimpleNamespace(author=sg.MessageAuthor.AGENT, content="sync reply")
        )
        acp.handle_rpc_request = AsyncMock(
            return_value=[reply_msg]
        )  # message/send result
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )

        inbound = sg.InboundSlack(
            team_id="T",
            channel="C1",
            user="U",
            text="2+2?",
            thread_ts="1",
            selector=None,
        )
        reply = await SlackGatewayUseCase()._dispatch(
            Target("math-agent"), inbound, "2+2?", None, {}
        )

        acp.handle_rpc_request.assert_awaited_once()
        call = acp.handle_rpc_request.await_args
        assert call.kwargs["method"] == AgentRPCMethod.MESSAGE_SEND
        assert call.kwargs["params"].task_name == "slack:1"
        assert reply == "sync reply"  # extracted from the message/send result directly

    @staticmethod
    def _sync_race_acp(monkeypatch, side_effect):
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        monkeypatch.setattr(
            sg, "_CREATE_RACE_BACKOFF_S", 0.0
        )  # no real sleeps in tests
        acp, _ = _fake_acp(acp_type=sg.ACPType.SYNC)
        acp.handle_rpc_request = AsyncMock(side_effect=side_effect)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        return acp

    @pytest.mark.asyncio
    async def test_sync_agent_retries_message_send_on_create_race(self, monkeypatch):
        # Two first messages for the same thread race on the globally-unique task name;
        # the loser's message/send raises DuplicateItemError. It must retry (get-or-create
        # now finds the winner's task) rather than drop the turn.
        reply_msg = SimpleNamespace(
            content=SimpleNamespace(author=sg.MessageAuthor.AGENT, content="ok")
        )
        acp = self._sync_race_acp(
            monkeypatch, [sg.DuplicateItemError("name taken"), [reply_msg]]
        )
        inbound = sg.InboundSlack(
            team_id="T", channel="C1", user="U", text="hi", thread_ts="1", selector=None
        )
        reply = await SlackGatewayUseCase()._dispatch(
            Target("math-agent"), inbound, "hi", None, {}
        )
        assert acp.handle_rpc_request.await_count == 2  # first raised, retry succeeded
        assert reply == "ok"  # the retry's reply, not a dropped turn

    @pytest.mark.asyncio
    async def test_sync_agent_retries_through_replica_lag(self, monkeypatch):
        # A single retry can still miss the winner's task if the read replica lags, so
        # the retry races the create AGAIN. Keep retrying until replication catches up.
        reply_msg = SimpleNamespace(
            content=SimpleNamespace(author=sg.MessageAuthor.AGENT, content="ok")
        )
        acp = self._sync_race_acp(
            monkeypatch,
            [
                sg.DuplicateItemError("race"),
                sg.DuplicateItemError("replica still lagging"),
                [reply_msg],
            ],
        )
        inbound = sg.InboundSlack(
            team_id="T", channel="C1", user="U", text="hi", thread_ts="1", selector=None
        )
        reply = await SlackGatewayUseCase()._dispatch(
            Target("math-agent"), inbound, "hi", None, {}
        )
        assert acp.handle_rpc_request.await_count == 3  # two misses, then success
        assert reply == "ok"

    @pytest.mark.asyncio
    async def test_sync_agent_gives_up_after_exhausting_retries(self, monkeypatch):
        # Persistent lag (all attempts dup) surfaces the error to _run_turn rather than
        # looping forever.
        monkeypatch.setattr(sg, "_CREATE_RACE_ATTEMPTS", 3)
        acp = self._sync_race_acp(
            monkeypatch, [sg.DuplicateItemError("still racing")] * 3
        )
        inbound = sg.InboundSlack(
            team_id="T", channel="C1", user="U", text="hi", thread_ts="1", selector=None
        )
        with pytest.raises(sg.DuplicateItemError):
            await SlackGatewayUseCase()._dispatch(
                Target("math-agent"), inbound, "hi", None, {}
            )
        assert acp.handle_rpc_request.await_count == 3


@pytest.mark.unit
class TestRunTurn:
    @pytest.mark.asyncio
    async def test_relays_reply_with_attribution_for_non_golden_agent(
        self, monkeypatch
    ):
        """Non-golden agents have no Slack tools -> the gateway is the single writer, so
        it relays their reply with attribution."""
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc, "_resolve_target", AsyncMock(return_value=(Target("pr-bot"), "hi"))
        )
        monkeypatch.setattr(uc, "_dispatch", AsyncMock(return_value="the answer"))
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_deliver", deliver)
        inbound = sg.InboundSlack(
            team_id="T", channel="C", user="U", text="hi", thread_ts="1", selector="hi"
        )

        await uc._run_turn(inbound)

        text = deliver.await_args.args[1]
        assert "the answer" in text
        assert "via pr-bot" in text

    @pytest.mark.asyncio
    async def test_golden_agent_self_posts_without_relay(self, monkeypatch):
        """golden-agent posts its own reply via SlackBot, so the gateway does NOT relay
        (no _deliver) — it just fires the turn with collect=False. It DOES set the
        'thinking…' status (which clears when the agent posts). Uses config_id=None on
        purpose: the signal is the golden-agent NAME, not the config."""
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc,
            "_resolve_target",
            AsyncMock(return_value=(Target(sg._DEFAULT_AGENT_NAME), "hi")),
        )
        dispatch = AsyncMock(return_value="ignored")
        monkeypatch.setattr(uc, "_dispatch", dispatch)
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_deliver", deliver)
        status = AsyncMock()
        monkeypatch.setattr(uc, "_set_status", status)
        inbound = sg.InboundSlack(
            team_id="T", channel="C", user="U", text="hi", thread_ts="1", selector="hi"
        )

        await uc._run_turn(inbound)

        deliver.assert_not_awaited()  # gateway does NOT relay golden-agent's reply
        status.assert_awaited_once()  # but DOES show "thinking…" while it works
        assert "thinking" in status.await_args.args[1]
        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs.get("collect") is False  # fire, don't poll

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
        target, inbound_arg, prompt = dispatch.await_args.args[:3]
        assert target.agent_name == "golden-agent"
        assert inbound_arg.thread_ts == expected_thread
        assert prompt == expected_prompt
        # golden-agent self-posts via SlackBot, so the gateway doesn't relay.
        deliver.assert_not_awaited()


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

        target, inbound_arg, prompt = dispatch.await_args.args[:3]
        assert target.agent_name == "pr-bot"  # routed to the non-golden runtime
        assert prompt == "review PR 42"  # selector stripped
        assert "via pr-bot" in deliver.await_args.args[1]

    @pytest.mark.asyncio
    async def test_dispatch_looks_up_the_target_agent_by_name(self, monkeypatch):
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
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
        await SlackGatewayUseCase()._dispatch(Target("pr-bot"), inbound, "hi", None, {})

        # dispatch is agent-agnostic — it resolves whatever target it's given.
        acp.agent_repository.get.assert_awaited_once_with(name="pr-bot")


@pytest.mark.unit
class TestConfigIdResolution:
    """The SGP name -> config_id lookup used by _resolve_target (the cascade itself is
    covered in TestResolveTarget)."""

    @pytest.mark.asyncio
    async def test_resolve_config_id_queries_sgp_by_name_and_caches(self, monkeypatch):
        monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
        monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
        captured = {}

        class _Resp:
            status_code = 200

            def json(self):
                return {"items": [{"id": "cfg-123", "name": "my-config"}]}

        class _Client:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                captured.update(url=url, headers=headers, params=params)
                return _Resp()

        monkeypatch.setattr(sg.httpx, "AsyncClient", _Client)
        headers = {"x-api-key": "k", "x-selected-account-id": "acct1"}
        cid = await SlackGatewayUseCase()._resolve_config_id("my-config", headers)

        assert cid == "cfg-123"
        assert captured["url"].endswith("/v5/agent_configs")
        assert captured["params"] == {"name": "my-config"}
        assert captured["headers"]["x-api-key"] == "k"
        assert sg._cache_get(("acct1", "", "my-config")) == "cfg-123"  # cached

    @pytest.mark.asyncio
    async def test_resolve_config_id_none_without_base_or_key(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(sg, "_SGP_BASE_URL", "")
        assert await uc._resolve_config_id("x", {"x-api-key": "k"}) is None  # no base
        monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
        assert await uc._resolve_config_id("x", {}) is None  # no credential at all

    @pytest.mark.asyncio
    async def test_resolve_config_id_accepts_a_cookie_credential(self, monkeypatch):
        # REGRESSION: this used to require x-api-key, which the shared bot has and a
        # linked user does not — their acting headers carry a session cookie. That
        # made resolution silently return None for exactly the users this feature is
        # for, so they'd get the default config while a bot turn resolved the name.
        captured = {}

        class _Resp:
            status_code = 200

            def json(self):
                return {"items": [{"name": "my-config", "id": "cfg-7"}]}

        class _Client:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                captured.update(url=url, headers=headers, params=params)
                return _Resp()

        monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
        monkeypatch.setattr(sg.httpx, "AsyncClient", _Client)
        monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})

        headers = {
            "cookie": "_identityJwt=abc",
            "x-selected-account-id": "acct-1",
        }
        got = await SlackGatewayUseCase()._resolve_config_id("my-config", headers)
        assert got == "cfg-7"
        # The credential is forwarded as-is; the directory decides whether it likes it.
        assert captured["headers"]["cookie"] == "_identityJwt=abc"


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
            status_code = 200

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
    """Bot token / signing secret read straight from env / k8s-secret."""

    @pytest.mark.asyncio
    async def test_bot_token_from_env(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env")
        assert await SlackGatewayUseCase()._fetch_bot_token() == "xoxb-env"

    @pytest.mark.asyncio
    async def test_bot_token_absent_is_empty(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        assert await SlackGatewayUseCase()._fetch_bot_token() == ""

    @pytest.mark.asyncio
    async def test_signing_secret_from_env(self, monkeypatch):
        monkeypatch.setenv("SLACK_SIGNING_SECRET", "sign-env")
        assert await SlackGatewayUseCase()._fetch_signing_secret("A123") == "sign-env"

    @pytest.mark.asyncio
    async def test_signing_secret_absent_is_empty(self, monkeypatch):
        monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
        assert await SlackGatewayUseCase()._fetch_signing_secret("A123") == ""


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
    async def test_no_key_authz_off_is_dev_bypass(self, monkeypatch):
        # authz off (no AGENTEX_AUTH_URL) + no bot key -> local dev bypass, no principal.
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.delenv("AGENTEX_AUTH_URL", raising=False)
        principal, headers = await SlackGatewayUseCase()._acting_identity()
        assert principal is None
        assert headers == {}

    @pytest.mark.asyncio
    async def test_no_key_authz_on_fails_closed(self, monkeypatch):
        # authz on (AGENTEX_AUTH_URL set) + no bot key -> refuse to dispatch unauthenticated.
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setenv("AGENTEX_AUTH_URL", "http://auth")
        with pytest.raises(RuntimeError, match="refusing to dispatch"):
            await SlackGatewayUseCase()._acting_identity()

    @pytest.mark.asyncio
    async def test_sends_both_headers(self, monkeypatch):
        # Auth needs x-api-key AND x-selected-account-id together.
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "ssk_test")
        monkeypatch.setattr(sg, "_ACTING_ACCOUNT_ID", "acct_1")
        fake_authn = _patch_authn(monkeypatch)

        principal, headers = await SlackGatewayUseCase()._acting_identity()

        assert headers == {"x-api-key": "ssk_test", "x-selected-account-id": "acct_1"}
        fake_authn.verify_headers.assert_awaited_once_with(headers)
        assert principal.user_id == "u1"


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
    async def test_agents_command_opens_modal_when_trigger_id_present(
        self, monkeypatch
    ):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        opened = AsyncMock(return_value=True)
        monkeypatch.setattr(uc, "_open_agents_modal", opened)
        resp = await uc.handle_slash_command(
            body=b"",
            headers={},
            form={"command": "/agents", "trigger_id": "TR1", "channel_id": "C1"},
        )
        assert resp == {}  # empty 200; the modal opened out of band
        opened.assert_awaited_once_with("TR1", "C1")

    @pytest.mark.asyncio
    async def test_agents_command_falls_back_to_list_when_modal_fails(
        self, monkeypatch
    ):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_open_agents_modal", AsyncMock(return_value=False))
        monkeypatch.setattr(
            uc,
            "_list_agents",
            AsyncMock(
                return_value=[SimpleNamespace(name="pr-bot", description="Reviews PRs")]
            ),
        )
        resp = await uc.handle_slash_command(
            body=b"", headers={}, form={"command": "/agents", "trigger_id": "TR1"}
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


@pytest.mark.unit
class TestHandleInteraction:
    """The /agents modal's view_submission: post a breadcrumb, then build the SAME
    InboundSlack an @mention would and dispatch the turn (anchored on the breadcrumb)."""

    def _payload(self, agent="golden-agent", message="summarize this"):
        return {
            "type": "view_submission",
            "user": {"id": "U1"},
            "team": {"id": "T1"},
            "view": {
                "callback_id": "agents_modal",
                "private_metadata": "C1",
                "state": {
                    "values": {
                        "agent_block": {
                            "agent_select": {"selected_option": {"value": agent}}
                        },
                        "message_block": {"message_input": {"value": message}},
                    }
                },
            },
        }

    @pytest.mark.asyncio
    async def test_submission_posts_breadcrumb_and_schedules_turn(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        api = AsyncMock(return_value={"ok": True, "ts": "1700.5"})
        monkeypatch.setattr(uc, "_slack_api", api)
        bg = BackgroundTasks()
        result = await uc.handle_interaction(
            body=b"",
            headers={},
            form={"payload": json.dumps(self._payload())},
            background=bg,
        )
        assert result == {}  # empty 200 closes the modal
        # breadcrumb: reconstructed command as the body, attribution as a context footer
        method, payload = api.await_args.args
        assert method == "chat.postMessage"
        assert payload["channel"] == "C1"
        assert "@agentex golden-agent summarize this" in payload["text"]
        footer = payload["blocks"][-1]
        assert footer["type"] == "context"
        footer_text = footer["elements"][0]["text"]
        assert "<@U1>" in footer_text and "golden-agent" in footer_text
        # turn scheduled with an InboundSlack that mirrors an @mention
        assert len(bg.tasks) == 1
        inbound = bg.tasks[0].args[0]
        assert inbound.selector == "golden-agent"
        assert inbound.text == "golden-agent summarize this"
        assert inbound.thread_ts == "1700.5"  # reply threads under the breadcrumb
        assert inbound.channel == "C1"
        assert inbound.user == "U1"

    @pytest.mark.asyncio
    async def test_breadcrumb_failure_returns_modal_error(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc,
            "_slack_api",
            AsyncMock(return_value={"ok": False, "error": "not_in_channel"}),
        )
        bg = BackgroundTasks()
        result = await uc.handle_interaction(
            body=b"",
            headers={},
            form={"payload": json.dumps(self._payload())},
            background=bg,
        )
        assert result["response_action"] == "errors"
        assert "message_block" in result["errors"]
        assert len(bg.tasks) == 0  # not-in-channel -> no turn dispatched

    @pytest.mark.asyncio
    async def test_missing_message_returns_error_without_posting(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        api = AsyncMock()
        monkeypatch.setattr(uc, "_slack_api", api)
        bg = BackgroundTasks()
        result = await uc.handle_interaction(
            body=b"",
            headers={},
            form={"payload": json.dumps(self._payload(message=""))},
            background=bg,
        )
        assert result["response_action"] == "errors"
        api.assert_not_awaited()  # no breadcrumb attempted
        assert len(bg.tasks) == 0

    @pytest.mark.asyncio
    async def test_non_modal_interaction_is_ignored(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", True)
        uc = SlackGatewayUseCase()
        api = AsyncMock()
        monkeypatch.setattr(uc, "_slack_api", api)
        bg = BackgroundTasks()
        form = {
            "payload": json.dumps(
                {"type": "block_actions", "view": {"callback_id": "other"}}
            )
        }
        result = await uc.handle_interaction(
            body=b"", headers={}, form=form, background=bg
        )
        assert result == {}
        api.assert_not_awaited()
        assert len(bg.tasks) == 0

    @pytest.mark.asyncio
    async def test_bad_signature_drops(self, monkeypatch):
        monkeypatch.setattr(sg, "_DEV_SKIP_VERIFY", False)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(uc, "_fetch_signing_secret", AsyncMock(return_value="shh"))
        api = AsyncMock()
        monkeypatch.setattr(uc, "_slack_api", api)
        bg = BackgroundTasks()
        form = {"payload": json.dumps({"api_app_id": "A1", **self._payload()})}
        result = await uc.handle_interaction(
            body=b"whatever",
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "v0=bad",
            },
            form=form,
            background=bg,
        )
        assert result == {}
        api.assert_not_awaited()
        assert len(bg.tasks) == 0

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


def _resolved(sgp_user_id="sgp-user-1", sgp_account_id="acct-1"):
    """Stand-in for a ResolvedIdentity."""
    return SimpleNamespace(
        sgp_user_id=sgp_user_id,
        sgp_account_id=sgp_account_id,
        principal={"user_id": sgp_user_id, "account_id": sgp_account_id},
    )


@pytest.mark.unit
class TestTurnIdentity:
    """Whose credential gets forwarded. This is the whole feature: the key on the
    delegation headers is what makes the agent's tools resolve that person's own
    Notion/Linear rather than a shared account's."""

    @staticmethod
    def _uc(monkeypatch, *, identity, headers):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc,
            "_acting_identity",
            AsyncMock(return_value=({"user_id": "bot"}, {"x-api-key": "sk_bot"})),
        )
        monkeypatch.setattr(
            uc, "_resolve_invoking_identity", AsyncMock(return_value=identity)
        )
        monkeypatch.setattr(
            uc,
            "_identity_link_service",
            MagicMock(
                return_value=SimpleNamespace(
                    acting_headers=AsyncMock(return_value=headers)
                )
            ),
        )
        return uc

    @pytest.mark.asyncio
    async def test_linked_user_forwards_their_own_key(self, monkeypatch):
        user_headers = {"x-api-key": "ssk_is_theirs", "x-selected-account-id": "acct-1"}
        uc = self._uc(monkeypatch, identity=_resolved(), headers=user_headers)

        principal, headers, sgp_user_id = await uc._turn_identity(_inbound())

        assert principal == {"user_id": "sgp-user-1", "account_id": "acct-1"}
        assert headers == user_headers  # THEIR key, not the bot's
        assert sgp_user_id == "sgp-user-1"

    @pytest.mark.asyncio
    async def test_unlinked_user_falls_back_to_the_bot(self, monkeypatch):
        monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", False)
        uc = self._uc(monkeypatch, identity=None, headers=None)

        principal, headers, sgp_user_id = await uc._turn_identity(_inbound())

        assert principal == {"user_id": "bot"}
        assert headers == {"x-api-key": "sk_bot"}
        # None keeps the legacy thread-wide task key, so in-flight conversations
        # aren't orphaned by enabling this.
        assert sgp_user_id is None

    @pytest.mark.asyncio
    async def test_linked_but_unusable_credential_falls_back(self, monkeypatch):
        # Linked with an expired / undecryptable / absent key: acting_headers returns
        # None, and the turn still runs — just without personal integrations.
        monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", False)
        uc = self._uc(monkeypatch, identity=_resolved(), headers=None)

        principal, headers, sgp_user_id = await uc._turn_identity(_inbound())

        assert principal == {"user_id": "bot"}
        assert sgp_user_id is None

    @pytest.mark.asyncio
    async def test_refuses_when_linking_is_required(self, monkeypatch):
        monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", True)
        uc = self._uc(monkeypatch, identity=None, headers=None)

        assert await uc._turn_identity(_inbound()) == (None, None, None)

    @pytest.mark.asyncio
    async def test_resolution_failure_propagates_rather_than_falling_back(
        self, monkeypatch
    ):
        # Silently running as the bot because the DB hiccuped is indistinguishable
        # from "this person isn't linked", and the two need different handling.
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc, "_resolve_invoking_identity", AsyncMock(side_effect=OSError("db down"))
        )
        with pytest.raises(OSError):
            await uc._turn_identity(_inbound())

    @pytest.mark.asyncio
    async def test_required_and_unlinked_tells_the_user_and_does_not_dispatch(
        self, monkeypatch
    ):
        monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", True)
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(
            uc, "_turn_identity", AsyncMock(return_value=(None, None, None))
        )
        dispatch = AsyncMock()
        deliver = AsyncMock()
        monkeypatch.setattr(uc, "_dispatch", dispatch)
        monkeypatch.setattr(uc, "_deliver", deliver)

        await uc._run_turn(_inbound())

        dispatch.assert_not_awaited()
        assert "connect your account" in deliver.await_args.args[1].lower()


@pytest.mark.unit
class TestTaskName:
    """Task-per-(thread, user) for linked users: one task can't be owned by two
    people, and a task holding only one user's turns removes the reply-attribution
    race the shared-task design had."""

    def test_linked_user_gets_a_per_user_task(self):
        uc = SlackGatewayUseCase()
        assert (
            uc._task_name(_inbound(thread_ts="1700.1"), "sgp-user-1")
            == "slack:T1:C1:1700.1:sgp-user-1"
        )

    def test_two_users_in_one_thread_get_separate_tasks(self):
        uc = SlackGatewayUseCase()
        inbound = _inbound(thread_ts="1700.1")
        assert uc._task_name(inbound, "sgp-a") != uc._task_name(inbound, "sgp-b")

    def test_same_user_and_thread_ts_in_two_workspaces_do_not_collide(self):
        # task/create is get-or-create on the name, so a collision merges two
        # conversations: prompts, metadata, agent config and account context all land
        # in one task. thread_ts is unique within a workspace but nothing makes it
        # unique across workspaces, and this gateway is multi-workspace.
        uc = SlackGatewayUseCase()
        a = uc._task_name(_inbound(team_id="T_A", thread_ts="1700.1"), "sgp-1")
        b = uc._task_name(_inbound(team_id="T_B", thread_ts="1700.1"), "sgp-1")
        assert a != b

    def test_same_user_and_thread_ts_in_two_channels_do_not_collide(self):
        uc = SlackGatewayUseCase()
        a = uc._task_name(_inbound(channel="C_A", thread_ts="1700.1"), "sgp-1")
        b = uc._task_name(_inbound(channel="C_B", thread_ts="1700.1"), "sgp-1")
        assert a != b

    def test_empty_thread_ts_still_scopes_to_workspace_channel_and_user(self):
        # normalize() falls back to "" when an event carries neither thread_ts nor
        # ts. Team and channel keep that from collapsing every such turn into one
        # global task; it degrades to one task per (workspace, channel, user).
        uc = SlackGatewayUseCase()
        a = uc._task_name(_inbound(team_id="T_A", channel="C_A", thread_ts=""), "sgp-1")
        b = uc._task_name(_inbound(team_id="T_B", channel="C_A", thread_ts=""), "sgp-1")
        c = uc._task_name(_inbound(team_id="T_A", channel="C_B", thread_ts=""), "sgp-1")
        assert len({a, b, c}) == 3

    def test_unlinked_user_keeps_the_legacy_thread_wide_key(self):
        # Unchanged on purpose: widening it would re-key threads already in flight.
        # It carries the same cross-workspace weakness, which predates this work.
        uc = SlackGatewayUseCase()
        assert uc._task_name(_inbound(thread_ts="1700.1"), None) == "slack:1700.1"


@pytest.mark.unit
class TestDispatchAttribution:
    @pytest.mark.asyncio
    async def test_first_turn_records_who_asked(self, monkeypatch):
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        acp, _ = _fake_acp(existing_task=None)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )

        await SlackGatewayUseCase()._dispatch(
            Target("golden-agent"),
            _inbound(user="U1", thread_ts="1"),
            "hi",
            None,
            {},
            sgp_user_id="sgp-user-1",
        )

        create = acp.handle_rpc_request.await_args_list[0].kwargs["params"]
        assert (
            create.name == "slack:T1:C1:1:sgp-user-1"
        )  # per (workspace, channel, thread, user)
        assert create.task_metadata["slack_user_id"] == "U1"
        assert create.task_metadata["sgp_user_id"] == "sgp-user-1"

    @pytest.mark.asyncio
    async def test_unlinked_first_turn_omits_the_sgp_user_id(self, monkeypatch):
        monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
        monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
        acp, _ = _fake_acp(existing_task=None)
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            MagicMock(return_value=acp),
        )
        monkeypatch.setattr(
            SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
        )

        await SlackGatewayUseCase()._dispatch(
            Target("golden-agent"), _inbound(thread_ts="1"), "hi", None, {}
        )

        create = acp.handle_rpc_request.await_args_list[0].kwargs["params"]
        assert create.name == "slack:1"
        assert "sgp_user_id" not in create.task_metadata


@pytest.mark.unit
@pytest.mark.asyncio
class TestLinkOffer:
    """DMing an unlinked user a connect link.

    The security-critical property under test is that the link goes to a DM and
    NOWHERE else. The nonce is a bearer token: whoever opens it gets linked to this
    Slack identity by signing in as themselves, so a link posted in a channel lets
    the first reader bind someone else's Slack identity to their own SGP account.
    """

    def _wire(self, monkeypatch, *, allowed=True, cooldown_ok=True, open_ok=True):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(sg, "_PUBLIC_BASE_URL", "https://agentex.example.com")
        monkeypatch.setattr(
            sg, "slack_user_profile", AsyncMock(return_value={"display_name": "@ada"})
        )
        monkeypatch.setattr(
            uc, "_claim_offer_cooldown", AsyncMock(return_value=cooldown_ok)
        )

        nonce = MagicMock()
        nonce.create_or_reuse = AsyncMock(return_value=("TOKEN123", False))
        nonce.claim_send = AsyncMock(return_value=allowed)
        monkeypatch.setattr(
            "src.domain.services.link_nonce_service.LinkNonceService",
            lambda *a, **k: nonce,
        )

        def _api(method, payload):
            if method == "conversations.open":
                return (
                    {"ok": True, "channel": {"id": "D_DM"}}
                    if open_ok
                    else {"ok": False, "error": "cannot_dm_bot"}
                )
            return {"ok": True}

        api = AsyncMock(side_effect=_api)
        monkeypatch.setattr(uc, "_slack_api", api)
        return uc, api, nonce

    async def test_dms_the_link_and_acknowledges_in_channel(self, monkeypatch):
        uc, api, _ = self._wire(monkeypatch)
        assert await uc._offer_link(_inbound()) is True

        calls = dict(c.args for c in api.await_args_list)
        assert set(calls) == {
            "conversations.open",
            "chat.postMessage",
            "chat.postEphemeral",
        }
        dm = calls["chat.postMessage"]
        assert dm["channel"] == "D_DM"
        assert "TOKEN123" in dm["text"]
        assert "/integrations/slack/link?nonce=" in dm["text"]
        # The nudge is ephemeral, so a channel isn't littered with one person's
        # onboarding.
        assert calls["chat.postEphemeral"]["user"] == "U1"

    async def test_the_link_is_never_broadcast(self, monkeypatch):
        """The invariant is single-viewer, not "not in the channel".

        The nonce is a bearer token, so the first reader of a channel-visible message
        could bind this user's Slack identity to their own SGP account. It may ride
        in the DM and in an ephemeral — both of which exactly one person can see —
        but a chat.postMessage must never carry it anywhere but that user's own DM.
        """
        uc, api, _ = self._wire(monkeypatch)
        await uc._offer_link(_inbound(channel="C_PUBLIC"))

        for method, payload in (c.args for c in api.await_args_list):
            if method == "chat.postMessage":
                assert (
                    payload["channel"] == "D_DM"
                ), f"the nonce was posted to {payload['channel']}, not the DM"
        # Nothing that lands in channel history mentions it.
        broadcast = [
            p
            for m, p in (c.args for c in api.await_args_list)
            if m == "chat.postMessage"
        ]
        assert all(
            "TOKEN123" not in str(p) or p["channel"] == "D_DM" for p in broadcast
        )

    async def test_dm_warns_against_forwarding(self, monkeypatch):
        uc, api, _ = self._wire(monkeypatch)
        await uc._offer_link(_inbound())
        dm = next(
            p
            for m, p in (c.args for c in api.await_args_list)
            if m == "chat.postMessage"
        )
        assert "forward" in dm["text"].lower()

    async def test_no_offer_without_a_public_base_url(self, monkeypatch):
        uc, api, _ = self._wire(monkeypatch)
        monkeypatch.setattr(sg, "_PUBLIC_BASE_URL", "")
        # A link the user can't reach is worse than no link.
        assert await uc._offer_link(_inbound()) is False
        api.assert_not_awaited()

    async def test_failed_dm_does_not_fall_back_to_the_channel(self, monkeypatch):
        uc, api, _ = self._wire(monkeypatch, open_ok=False)
        assert await uc._offer_link(_inbound()) is False
        for _method, payload in (c.args for c in api.await_args_list):
            assert "TOKEN123" not in str(payload)

    async def test_send_cap_reached_says_so_without_a_second_dm(self, monkeypatch):
        uc, api, _ = self._wire(monkeypatch, allowed=False)
        assert await uc._offer_link(_inbound()) is False
        methods = [m for m, _ in (c.args for c in api.await_args_list)]
        # Acknowledge in-channel rather than going silent, but send no new DM.
        # conversations.open still runs first — it's idempotent, and this branch
        # needs the channel id to deep-link the user to the DM they can't find.
        assert methods == ["conversations.open", "chat.postEphemeral"]
        assert "chat.postMessage" not in methods

    async def test_cooldown_suppresses_the_offer_entirely(self, monkeypatch):
        uc, api, nonce = self._wire(monkeypatch, cooldown_ok=False)
        assert await uc._offer_link(_inbound()) is False
        nonce.create_or_reuse.assert_not_awaited()
        api.assert_not_awaited()

    async def test_redis_failure_is_swallowed(self, monkeypatch):
        # The turn is already proceeding; a nonce-store outage must not break it.
        uc, api, nonce = self._wire(monkeypatch)
        nonce.create_or_reuse = AsyncMock(side_effect=RuntimeError("redis down"))
        assert await uc._offer_link(_inbound()) is False

    async def test_pending_turn_is_stashed_for_later_replay(self, monkeypatch):
        uc, _api, nonce = self._wire(monkeypatch)
        await uc._offer_link(_inbound(text="what's in my linear?", channel="C9"))
        req = nonce.create_or_reuse.await_args.args[0]
        assert req.external_user_id == "U1"
        assert req.pending_turn["text"] == "what's in my linear?"
        assert req.pending_turn["channel"] == "C9"


@pytest.mark.unit
@pytest.mark.asyncio
class TestLinkOfferDiscoverability:
    """The offer has to be findable, not merely delivered.

    Observed in production on the first real offer: the DM was posted successfully
    and confirmed present via conversations.history, and the recipient still reported
    never receiving it — because Slack files bot conversations under "Apps" rather
    than in the Direct messages list. "Check your DMs" points at the one place the
    message isn't, so the ephemeral carries a deep link into the conversation.
    """

    def _wire(self, monkeypatch, *, allowed=True):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(sg, "_PUBLIC_BASE_URL", "https://agentex.example.com")
        monkeypatch.setattr(
            sg, "slack_user_profile", AsyncMock(return_value={"display_name": "@ada"})
        )
        monkeypatch.setattr(uc, "_claim_offer_cooldown", AsyncMock(return_value=True))
        nonce = MagicMock()
        nonce.create_or_reuse = AsyncMock(return_value=("TOKEN123", False))
        nonce.claim_send = AsyncMock(return_value=allowed)
        monkeypatch.setattr(
            "src.domain.services.link_nonce_service.LinkNonceService",
            lambda *a, **k: nonce,
        )
        api = AsyncMock(
            side_effect=lambda m, p: (
                {"ok": True, "channel": {"id": "D_DM"}}
                if m == "conversations.open"
                else {"ok": True}
            )
        )
        monkeypatch.setattr(uc, "_slack_api", api)
        return uc, api

    def _ephemeral(self, api):
        return next(
            p
            for m, p in (c.args for c in api.await_args_list)
            if m == "chat.postEphemeral"
        )

    async def test_ephemeral_points_at_the_durable_copy(self, monkeypatch):
        # The link is inline now, so the deep link is no longer how you reach it —
        # it's the pointer to the copy that survives a reload, since ephemerals
        # don't. app_redirect rather than a slack:// URI, which fails on web.
        uc, api = self._wire(monkeypatch)
        await uc._offer_link(_inbound(team_id="T_ACME"))

        text = self._ephemeral(api)["text"]
        assert "https://slack.com/app_redirect?channel=D_DM&team=T_ACME" in text
        assert "TOKEN123" in text

    async def test_the_ephemeral_carries_the_link_itself(self, monkeypatch):
        # Same audience as the DM (one person), and it's where the user is already
        # looking — which is the whole point, since bot DMs are filed under "Apps"
        # where people don't think to look.
        uc, api = self._wire(monkeypatch)
        await uc._offer_link(_inbound())
        eph = self._ephemeral(api)
        assert "TOKEN123" in eph["text"]
        assert eph["user"] == "U1"
        # Still says where the durable copy is, since ephemerals vanish on reload.
        assert "app_redirect" in eph["text"]

    async def test_send_cap_ephemeral_also_deep_links(self, monkeypatch):
        # The "already sent" path is exactly when someone can't find the DM, so it
        # needs the link more than the happy path does.
        uc, api = self._wire(monkeypatch, allowed=False)
        assert await uc._offer_link(_inbound(team_id="T_ACME")) is False

        text = self._ephemeral(api)["text"]
        # Past the DM cap the user still gets the live link — the cap limits DMs,
        # not what we're allowed to show the person in front of us.
        assert "TOKEN123" in text
        assert "https://slack.com/app_redirect?channel=D_DM&team=T_ACME" in text
        # But no second DM.
        methods = [m for m, _ in (c.args for c in api.await_args_list)]
        assert "chat.postMessage" not in methods

    async def test_unreachable_dm_offers_nothing(self, monkeypatch):
        # If we can't open the DM we can't link to it either, so pointing someone at
        # a conversation that doesn't exist would be worse than staying quiet.
        uc, api = self._wire(monkeypatch)
        monkeypatch.setattr(
            uc,
            "_slack_api",
            AsyncMock(return_value={"ok": False, "error": "cannot_dm_bot"}),
        )
        assert await uc._offer_link(_inbound()) is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestStoredCredentialStillAccepted:
    """A stored session can die before its recorded expiry — and a rejection is not
    the same thing as a failure.

    credential_expires_at is an upper bound. Sign out and the JWT stops being
    honoured while the stored expiry still reads months away, so without this check
    the gateway hands the agent a dead cookie, every user-scoped tool call 401s, and
    nothing prompts a re-link because locally the credential looks fine.

    The trap is over-applying it. A misconfigured or down auth service rejects
    EVERYONE, and concluding "your credential is bad" would tell a whole workspace to
    re-link — fixing nothing, since nothing is wrong with their credentials. The
    adapter's exception types carry the distinction: ClientError (4xx) is a refusal
    of this credential; ServiceError (5xx) and anything else mean the check broke.
    """

    def _verify(self, monkeypatch, raises=None, auth_url="http://auth.test"):
        """Stub the verifier, and the env RESOLVER rather than os.environ.

        resolve_environment_variable_dependency reads a GlobalDependencies singleton
        built once per process, so monkeypatch.setenv never reaches it — a test that
        set the variable would silently take the "authz disabled" path and pass for
        the wrong reason.
        """
        import src.adapters.authentication.adapter_agentex_authn_proxy as ap
        import src.config.dependencies as deps

        async def verify(_self, _headers):
            if raises is not None:
                raise raises
            return {"user_id": "sgp-1"}

        monkeypatch.setattr(ap.AgentexAuthenticationProxy, "verify_headers", verify)
        monkeypatch.setattr(
            deps,
            "resolve_environment_variable_dependency",
            lambda key: auth_url if "AUTH_URL" in str(key) else "development",
        )

    @staticmethod
    def _identity():
        return SimpleNamespace(sgp_user_id="sgp-1")

    @staticmethod
    def _headers():
        return {"cookie": "_identityJwt=abc", "x-selected-account-id": "acct-1"}

    async def test_accepted_credential_is_usable(self, monkeypatch):
        self._verify(monkeypatch)
        uc = SlackGatewayUseCase()
        assert await uc._credential_still_accepted(self._identity(), self._headers())

    async def test_401_means_relink(self, monkeypatch):
        from src.adapters.authentication.exceptions import AuthenticationError

        self._verify(monkeypatch, raises=AuthenticationError("revoked"))
        uc = SlackGatewayUseCase()
        assert not await uc._credential_still_accepted(
            self._identity(), self._headers()
        )

    async def test_403_also_means_relink(self, monkeypatch):
        # A valid session that can no longer use the stored account needs a re-link
        # to capture a current one.
        from src.domain.exceptions import ClientError

        class Forbidden(ClientError):
            code = 403

        self._verify(monkeypatch, raises=Forbidden("not in account"))
        uc = SlackGatewayUseCase()
        assert not await uc._credential_still_accepted(
            self._identity(), self._headers()
        )

    @pytest.mark.parametrize(
        "exc_name",
        ["AuthenticationGatewayError", "AuthenticationServiceUnavailableError"],
    )
    async def test_service_errors_do_not_blame_the_credential(
        self, monkeypatch, exc_name
    ):
        # 5xx from the verifier means the CHECK failed. Revoking everyone's access
        # because a verification dependency is unwell is the outage-amplifying move.
        import src.adapters.authentication.exceptions as exceptions

        self._verify(monkeypatch, raises=getattr(exceptions, exc_name)("upstream"))
        uc = SlackGatewayUseCase()
        assert await uc._credential_still_accepted(self._identity(), self._headers())

    @pytest.mark.parametrize("exc", [TimeoutError("slow"), RuntimeError("surprise")])
    async def test_unexpected_failures_assume_the_credential_is_fine(
        self, monkeypatch, exc
    ):
        self._verify(monkeypatch, raises=exc)
        uc = SlackGatewayUseCase()
        assert await uc._credential_still_accepted(self._identity(), self._headers())

    async def test_skipped_entirely_when_authz_is_off(self, monkeypatch):
        # Local dev with no auth service: nothing to verify against, and refusing
        # every credential would make the feature untestable offline.
        from src.adapters.authentication.exceptions import AuthenticationError

        # Would reject if it were ever called — so a pass proves it wasn't.
        self._verify(monkeypatch, raises=AuthenticationError("nope"), auth_url="")
        uc = SlackGatewayUseCase()
        assert await uc._credential_still_accepted(self._identity(), self._headers())

    async def test_rejection_falls_back_to_the_bot_and_prompts(self, monkeypatch):
        # End to end: a rejected credential must yield sgp_user_id=None, because that
        # is precisely the condition _run_turn uses to offer a re-link.
        from src.adapters.authentication.exceptions import AuthenticationError

        uc = SlackGatewayUseCase()
        identity = SimpleNamespace(
            sgp_user_id="sgp-1", principal={"user_id": "sgp-1"}, sgp_account_id="acct-1"
        )
        monkeypatch.setattr(
            uc, "_resolve_invoking_identity", AsyncMock(return_value=identity)
        )
        monkeypatch.setattr(
            uc,
            "_identity_link_service",
            lambda: SimpleNamespace(
                acting_headers=AsyncMock(return_value=self._headers())
            ),
        )
        self._verify(monkeypatch, raises=AuthenticationError("revoked"))
        monkeypatch.setattr(
            uc, "_acting_identity", AsyncMock(return_value=("bot", {"x-api-key": "k"}))
        )
        monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", False)

        principal, headers, sgp_user_id = await uc._turn_identity(_inbound())

        assert principal == "bot"
        assert headers == {"x-api-key": "k"}
        assert sgp_user_id is None  # <- what makes _run_turn offer a re-link

    async def test_credential_is_not_deleted_on_rejection(self, monkeypatch):
        # Non-destructive on purpose: a systemic 401 costs a bot-fallback turn and a
        # rate-limited nudge, then recovers by itself. Tombstoning rows would not.
        from src.adapters.authentication.exceptions import AuthenticationError

        uc = SlackGatewayUseCase()
        repo = MagicMock()
        service = SimpleNamespace(
            acting_headers=AsyncMock(return_value=self._headers()), repository=repo
        )
        monkeypatch.setattr(
            uc,
            "_resolve_invoking_identity",
            AsyncMock(
                return_value=SimpleNamespace(
                    sgp_user_id="sgp-1", principal={}, sgp_account_id="a"
                )
            ),
        )
        monkeypatch.setattr(uc, "_identity_link_service", lambda: service)
        self._verify(monkeypatch, raises=AuthenticationError("revoked"))
        monkeypatch.setattr(uc, "_acting_identity", AsyncMock(return_value=("bot", {})))
        monkeypatch.setattr(sg, "_REQUIRE_LINKED_USER", False)

        await uc._turn_identity(_inbound())

        repo.revoke.assert_not_called()
        assert not any(
            "revoke" in str(c) or "delete" in str(c) for c in repo.mock_calls
        )


@pytest.mark.unit
class TestUnlinkedTurnContext:
    """An unlinked turn must tell the agent it isn't the user.

    Without it the turn runs on the shared bot identity and can't tell, so it reports
    on ITS OWN access as though it were the asker's. Observed in production:
    confidently "no Linear access, verified two ways" plus an overstated GitHub claim,
    while the gateway was simultaneously DMing that person a connect link. Two
    messages that contradicted each other, one of them wrong about the user.

    It also removes the reason the agent invents its own OAuth link — a URL with a
    localhost redirect, which cannot work from Slack and reads like a real
    instruction.
    """

    def test_unlinked_context_disclaims_personal_access(self):
        text = sg._turn_content(_inbound(), "what's in my linear?", unlinked=True)
        assert "NOT running as the person" in text
        # Must not let the agent pass its own reach off as the user's.
        assert "personal integrations" in text
        assert "as if it were theirs" in text

    def test_unlinked_context_forbids_inventing_oauth_links(self):
        text = sg._turn_content(_inbound(), "hi", unlinked=True)
        assert "do NOT generate authorization or OAuth links" in text
        # And explains why there's no need: one is already on its way.
        assert "ALREADY been sent a link" in text

    def test_linked_turn_says_none_of_it(self):
        text = sg._turn_content(_inbound(), "what's in my linear?", unlinked=False)
        assert "NOT running as the person" not in text
        assert "OAuth" not in text

    def test_channel_context_survives_either_way(self):
        # The disclaimer is additive: the agent still needs the channel id to read
        # thread history with its Slack tools.
        for unlinked in (True, False):
            text = sg._turn_content(_inbound(channel="C9"), "hi", unlinked=unlinked)
            assert "channel_id=C9" in text

    def test_composes_with_the_self_posts_directive(self):
        # golden-agent is both self-posting AND commonly unlinked; it needs both.
        text = sg._turn_content(_inbound(), "hi", self_posts=True, unlinked=True)
        assert "post_message" in text
        assert "NOT running as the person" in text

    def test_user_prompt_is_still_last(self):
        # The prompt must follow the context, or the agent reads the directives as
        # part of the question.
        text = sg._turn_content(_inbound(), "MY QUESTION", unlinked=True)
        assert text.rstrip().endswith("MY QUESTION")


@pytest.mark.unit
@pytest.mark.asyncio
class TestUnlinkedFlagIsWiredToIdentity:
    """The flag tracks sgp_user_id — the same signal that offers the link — so the
    agent is told it's unlinked exactly when the user is being asked to link, and the
    two messages agree instead of contradicting each other."""

    @staticmethod
    def _acp(monkeypatch):
        acp = MagicMock()
        acp.agent_repository = MagicMock(get=AsyncMock(return_value=MagicMock()))
        # Fails AFTER _turn_content has been built, which is all this test needs.
        acp.handle_rpc_request = AsyncMock(side_effect=RuntimeError("stop here"))
        monkeypatch.setattr(
            "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
            lambda *a, **k: acp,
        )

    @pytest.mark.parametrize(
        "sgp_user_id, expect_unlinked", [("sgp-1", False), (None, True)]
    )
    async def test_flag_mirrors_whether_the_turn_runs_as_a_person(
        self, monkeypatch, sgp_user_id, expect_unlinked
    ):
        captured = {}

        def fake_turn_content(inbound, prompt, *, self_posts=False, unlinked=False):
            captured["unlinked"] = unlinked
            return "ctx"

        monkeypatch.setattr(sg, "_turn_content", fake_turn_content)
        self._acp(monkeypatch)

        with contextlib.suppress(Exception):
            await SlackGatewayUseCase()._dispatch(
                sg.Target(agent_name="golden-agent", config_id=None),
                _inbound(),
                "hi",
                {"user_id": "u"},
                {"x-api-key": "k"},
                sgp_user_id=sgp_user_id,
            )

        assert captured.get("unlinked") is expect_unlinked


@pytest.mark.unit
@pytest.mark.asyncio
class TestReplayPendingTurn:
    """Re-running the message that prompted a link."""

    def _wire(self, monkeypatch):
        uc = SlackGatewayUseCase()
        ran = {}

        async def run_turn(inbound, *, offer_link=True):
            ran["inbound"] = inbound
            ran["offer_link"] = offer_link

        monkeypatch.setattr(uc, "_run_turn", run_turn)
        monkeypatch.setattr(uc, "_set_status", AsyncMock())
        return uc, ran

    async def test_reconstructs_the_original_turn(self, monkeypatch):
        uc, ran = self._wire(monkeypatch)
        ok = await uc.replay_pending_turn(
            team_id="T1",
            user_id="U1",
            pending_turn={
                "text": "what's in my linear?",
                "channel": "C9",
                "thread_ts": "1700.1",
            },
        )
        assert ok
        inbound = ran["inbound"]
        assert (inbound.team_id, inbound.user) == ("T1", "U1")
        assert (inbound.channel, inbound.thread_ts) == ("C9", "1700.1")
        assert inbound.text == "what's in my linear?"

    async def test_selector_is_rederived_like_normalize(self, monkeypatch):
        # A selector-driven turn must resolve to the same target it would have; the
        # nonce stores only the text, so the selector is re-derived the same way.
        uc, ran = self._wire(monkeypatch)
        await uc.replay_pending_turn(
            team_id="T1",
            user_id="U1",
            pending_turn={"text": "some-config summarise this", "channel": "C1"},
        )
        assert ran["inbound"].selector == "some-config"

    async def test_never_offers_another_link(self, monkeypatch):
        # The loop guard. This turn exists BECAUSE they just linked; offering again
        # would mint a nonce, DM a link, and invite the same loop on the next click.
        uc, ran = self._wire(monkeypatch)
        await uc.replay_pending_turn(
            team_id="T1", user_id="U1", pending_turn={"text": "hi", "channel": "C1"}
        )
        assert ran["offer_link"] is False

    async def test_sets_the_thinking_indicator(self, monkeypatch):
        # The answer lands minutes after the user clicked a web page, so without this
        # a reply appears out of nowhere.
        uc, _ran = self._wire(monkeypatch)
        await uc.replay_pending_turn(
            team_id="T1", user_id="U1", pending_turn={"text": "hi", "channel": "C1"}
        )
        uc._set_status.assert_awaited_once()

    @pytest.mark.parametrize(
        "pending",
        [
            None,
            {},
            {"text": "", "channel": "C1"},
            {"text": "hi", "channel": ""},
            {"text": "   ", "channel": "C1"},
        ],
    )
    async def test_incomplete_pending_turn_does_nothing(self, monkeypatch, pending):
        uc, ran = self._wire(monkeypatch)
        assert (
            await uc.replay_pending_turn(
                team_id="T1", user_id="U1", pending_turn=pending
            )
            is False
        )
        assert ran == {}

    async def test_missing_identity_does_nothing(self, monkeypatch):
        uc, ran = self._wire(monkeypatch)
        assert (
            await uc.replay_pending_turn(
                team_id="", user_id="U1", pending_turn={"text": "hi", "channel": "C1"}
            )
            is False
        )
        assert ran == {}


@pytest.mark.unit
@pytest.mark.asyncio
class TestOfferLinkSuppression:
    async def test_run_turn_skips_the_offer_when_told_to(self, monkeypatch):
        uc = SlackGatewayUseCase()
        offered = []
        monkeypatch.setattr(
            uc, "_offer_link", AsyncMock(side_effect=lambda i: offered.append(i))
        )
        # Unlinked: normally this is exactly when an offer fires.
        monkeypatch.setattr(
            uc,
            "_turn_identity",
            AsyncMock(return_value=("bot", {"x-api-key": "k"}, None)),
        )
        monkeypatch.setattr(
            uc, "_resolve_target", AsyncMock(side_effect=RuntimeError("stop"))
        )
        monkeypatch.setattr(uc, "_deliver", AsyncMock())

        await uc._run_turn(_inbound(), offer_link=False)
        assert offered == []

        await uc._run_turn(_inbound(), offer_link=True)
        assert len(offered) == 1


# --- route-level ack shape -------------------------------------------------
#
# Slack renders a slash-command / interaction response body verbatim, so "show
# nothing" has to be an EMPTY body. Returning {} from the route made FastAPI
# serialize a literal `{}`, which Slack printed in the channel after /agents had
# already opened its modal.


def test_slack_ack_empty_payload_sends_no_body():
    from src.api.routes.slack import _slack_ack

    resp = _slack_ack({})
    assert resp.status_code == 200
    assert resp.body == b""


def test_slack_ack_passes_through_a_real_message():
    from src.api.routes.slack import _slack_ack

    resp = _slack_ack({"response_type": "ephemeral", "text": "Unsupported command: /x"})
    assert resp.status_code == 200
    assert json.loads(resp.body) == {
        "response_type": "ephemeral",
        "text": "Unsupported command: /x",
    }


# --- per-user Slack config -------------------------------------------------
#
# An SGP agent_config belongs to whoever created it and is invisible to everyone
# else, and golden-agent reads the config AS THE TURN'S IDENTITY. So a linked
# user pointed at a shared config fails turn-1 resolution, the event is dropped,
# and Slack shows a hang. Each linked user therefore gets their own config named
# `slack-agentex-bot`, created on demand.


class _FakeSGP:
    """Stands in for SGP's agent_configs endpoints. Records POSTs."""

    def __init__(self, existing=(), create_status=200, create_id="new-cfg"):
        self.existing = list(existing)
        self.create_status = create_status
        self.create_id = create_id
        self.posts: list[dict] = []

    def client(self):
        outer = self

        class _Resp:
            def __init__(self, payload, status=200):
                self._p, self.status_code = payload, status

            def json(self):
                return self._p

        class _Client:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                return _Resp({"items": outer.existing})

            async def post(self, url, headers=None, json=None):
                outer.posts.append({"url": url, "headers": headers, "json": json})
                return _Resp({"id": outer.create_id}, outer.create_status)

        return _Client


def _user_headers(user_key: str, account: str = "acct1") -> dict[str, str]:
    return {"cookie": f"_identityJwt={user_key}", "x-selected-account-id": account}


@pytest.mark.asyncio
async def test_user_config_reuses_an_existing_one(monkeypatch):
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    fake = _FakeSGP(existing=[{"id": "mine-1", "name": sg._USER_CONFIG_NAME}])
    monkeypatch.setattr(sg.httpx, "AsyncClient", fake.client())

    cid = await SlackGatewayUseCase()._own_config_id(_user_headers("alice"), "u-alice")
    assert cid == "mine-1"
    assert fake.posts == []  # nothing created when one already exists


@pytest.mark.asyncio
async def test_user_config_is_created_when_absent(monkeypatch):
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    fake = _FakeSGP(existing=[], create_id="fresh-1")
    monkeypatch.setattr(sg.httpx, "AsyncClient", fake.client())

    cid = await SlackGatewayUseCase()._own_config_id(_user_headers("bob"), "u-bob")
    assert cid == "fresh-1"
    assert len(fake.posts) == 1
    body = fake.posts[0]["json"]
    assert body["name"] == sg._USER_CONFIG_NAME
    # Created as THEM, so it is theirs to read and edit.
    assert fake.posts[0]["headers"]["cookie"] == "_identityJwt=bob"
    # A shared-workspace bot has no business running shell commands.
    assert "Bash" not in body["allowed_tools"]
    assert "Write" not in body["allowed_tools"]


@pytest.mark.asyncio
async def test_two_users_do_not_share_a_cached_config_id(monkeypatch):
    """The regression the cache key exists to prevent.

    Config names are NOT unique and every linked user has one called
    `slack-agentex-bot`. Keyed by account alone, the first caller would populate
    the entry for everyone in that account and hand them all one person's config
    id — which then fails to read for all but its owner: the original hang, via a
    cache.
    """
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    uc = SlackGatewayUseCase()

    a = _FakeSGP(existing=[{"id": "alice-cfg", "name": sg._USER_CONFIG_NAME}])
    monkeypatch.setattr(sg.httpx, "AsyncClient", a.client())
    assert await uc._own_config_id(_user_headers("alice"), "u-alice") == "alice-cfg"

    b = _FakeSGP(existing=[{"id": "bob-cfg", "name": sg._USER_CONFIG_NAME}])
    monkeypatch.setattr(sg.httpx, "AsyncClient", b.client())
    assert await uc._own_config_id(_user_headers("bob"), "u-bob") == "bob-cfg"

    assert sg._cache_get(("acct1", "u-alice", sg._USER_CONFIG_NAME)) == "alice-cfg"
    assert sg._cache_get(("acct1", "u-bob", sg._USER_CONFIG_NAME)) == "bob-cfg"


@pytest.mark.asyncio
async def test_user_config_returns_none_when_creation_fails(monkeypatch):
    """Caller must be able to tell, so it can drop to the bot rather than point a
    linked user at a config they cannot read (which would be a silent drop)."""
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    fake = _FakeSGP(existing=[], create_status=403)
    monkeypatch.setattr(sg.httpx, "AsyncClient", fake.client())

    cid = await SlackGatewayUseCase()._own_config_id(_user_headers("carol"), "u-carol")
    assert cid is None


@pytest.mark.asyncio
async def test_resolve_target_prefers_the_users_own_config(monkeypatch):
    inbound = sg.InboundSlack(
        team_id="T1",
        channel="C1",
        user="U1",
        text="hello",
        selector="",
        thread_ts="1.0",
    )
    monkeypatch.setattr(sg, "_DEFAULT_CONFIG_ID", "shared-default")
    target, prompt = await SlackGatewayUseCase()._resolve_target(
        inbound, {}, sgp_user_id="u-alice", user_config_id="alice-cfg"
    )
    assert target.config_id == "alice-cfg"
    assert prompt == "hello"


@pytest.mark.asyncio
async def test_resolve_target_uses_the_shared_default_when_unlinked(monkeypatch):
    """Unlinked turns run as the bot, which CAN read the shared config, so that
    path is deliberately unchanged."""
    inbound = sg.InboundSlack(
        team_id="T1",
        channel="C1",
        user="U1",
        text="hello",
        selector="",
        thread_ts="1.0",
    )
    monkeypatch.setattr(sg, "_DEFAULT_CONFIG_ID", "shared-default")
    target, _ = await SlackGatewayUseCase()._resolve_target(inbound, {})
    assert target.config_id == "shared-default"


def test_unlinked_turns_need_a_pinned_config_id():
    """The bot cannot resolve one by name: it may not create configs (403), and its
    credential can read EVERY config in the account, so a by-name match would return
    an arbitrary user's `slack-agentex-bot` once users start making their own."""
    assert sg._DEFAULT_CONFIG_ID == "" or sg._DEFAULT_CONFIG_ID


@pytest.mark.parametrize(
    "dd_env,expect_host",
    [("sgp-dev", True), ("sgp-prod", False), ("", False), ("staging", False)],
)
def test_dev_defaults_are_opt_in_by_exact_environment(monkeypatch, dd_env, expect_host):
    """An unset base URL must mean "no host", not "somebody else's host".

    auth_headers carry a live credential — a linked user's _identityJwt session
    cookie, or the bot's api key — and both SGP calls forward them verbatim. A default
    pointing at another environment would SEND those credentials there. Only a
    deployment that is demonstrably sgp-dev gets the baked-in host; everything else
    resolves to "" and makes no request at all.

    ENVIRONMENT is deliberately not the signal: the sgp-dev deployment reports
    ENVIRONMENT=staging, hence the "staging" case here expecting no host.
    """
    monkeypatch.delenv("SLACK_GATEWAY_SGP_BASE_URL", raising=False)
    monkeypatch.delenv("SLACK_GATEWAY_DEFAULT_CONFIG_ID", raising=False)
    monkeypatch.setenv("DD_ENV", dd_env)

    base, config_id = sg._resolve_sgp_base_url(), sg._resolve_default_config_id()

    if expect_host:
        assert base == sg._DEV_SGP_BASE_URL and config_id == sg._DEV_SGP_CONFIG_ID
    else:
        assert base == "" and config_id == "", "must fail closed, not fall back"


def test_explicit_configuration_always_wins(monkeypatch):
    monkeypatch.setenv("DD_ENV", "sgp-prod")
    monkeypatch.setenv("SLACK_GATEWAY_SGP_BASE_URL", "https://api.prod.example/")
    monkeypatch.setenv("SLACK_GATEWAY_DEFAULT_CONFIG_ID", "prod-cfg")
    assert (
        sg._resolve_sgp_base_url() == "https://api.prod.example"
    )  # trailing / trimmed
    assert sg._resolve_default_config_id() == "prod-cfg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sgp_user_id,expected",
    [
        (None, []),  # bot-run turn -> user-scoped MCPs withheld
        ("u-alice", None),  # linked turn  -> left to the config
    ],
)
async def test_bot_run_turns_withhold_user_scoped_mcps(
    monkeypatch, sgp_user_id, expected
):
    """No personal identity behind the turn -> no personal integrations.

    Leaving them on is worse than useless: the config's MCP list resolves against
    whoever the turn acts as, so the bot would either reach ITS OWN connected accounts
    while answering someone else's question, or resolve nothing and still start a
    server per MCP with an empty Authorization header. SlackBot is unaffected — it is
    auto-enabled by Slack origin, not requested here.
    """
    monkeypatch.setattr(sg, "_ACTING_BOT_API_KEY", "")
    monkeypatch.setattr(sg, "GlobalDependencies", MagicMock())
    monkeypatch.setattr(sg, "_DEFAULT_MCPS", [])
    acp, _ = _fake_acp(existing_task=None)
    monkeypatch.setattr(
        "src.temporal.scheduled_agent_run_factory.build_acp_use_case_for_principal",
        MagicMock(return_value=acp),
    )
    monkeypatch.setattr(
        SlackGatewayUseCase, "_collect_reply", AsyncMock(return_value=None)
    )
    inbound = sg.InboundSlack(
        team_id="T", channel="C1", user="U", text="hi", thread_ts="1.0", selector=None
    )
    await SlackGatewayUseCase()._dispatch(
        Target("golden-agent", config_id="cfg-1"),
        inbound,
        "hi",
        None,
        {},
        sgp_user_id=sgp_user_id,
    )
    params = acp.handle_rpc_request.await_args_list[0].kwargs["params"].params
    assert params["config_id"] == "cfg-1"
    if expected is None:
        assert "mcps" not in params
    else:
        assert params["mcps"] == expected


# --- watching a self-posting turn ------------------------------------------


class _Msg:
    def __init__(self, mid, author, text="hi"):
        self.id = mid
        self.content = SimpleNamespace(author=author, content=text, type="text")


@pytest.mark.asyncio
async def test_watch_says_something_when_the_turn_is_silent(monkeypatch):
    """A dead turn posts nothing and leaves "thinking…" up forever, which is
    indistinguishable from the agent still working — so nobody reports it."""
    monkeypatch.setattr(sg, "_GOLDEN_REPLY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sg, "_GOLDEN_REPLY_POLL_S", 0.01)
    uc = SlackGatewayUseCase()
    svc = MagicMock()
    svc.get_messages = AsyncMock(return_value=[])  # nothing ever appears
    status, delivered = [], []
    monkeypatch.setattr(
        uc, "_set_status", AsyncMock(side_effect=lambda i, s: status.append(s))
    )
    monkeypatch.setattr(
        uc, "_deliver", AsyncMock(side_effect=lambda i, t: delivered.append(t))
    )
    inbound = sg.InboundSlack(
        team_id="T", channel="C1", user="U", text="hi", thread_ts="1.0", selector=None
    )

    await uc._watch_self_posting_turn(svc, "task-1", set(), inbound)

    assert status == [""], "the indicator must be cleared first"
    assert len(delivered) == 1
    assert "didn't respond" in delivered[0]


@pytest.mark.asyncio
async def test_watch_stays_quiet_once_the_agent_talks(monkeypatch):
    """Returns on the first agent-authored text — a liveness signal, not completion.
    The agent posts to Slack itself and posting clears the indicator, so once it is
    talking there is nothing for the gateway to do."""
    monkeypatch.setattr(sg, "_GOLDEN_REPLY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sg, "_GOLDEN_REPLY_POLL_S", 0.01)
    uc = SlackGatewayUseCase()
    svc = MagicMock()
    svc.get_messages = AsyncMock(return_value=[_Msg("m2", "agent", "working on it")])
    monkeypatch.setattr(uc, "_set_status", AsyncMock())
    monkeypatch.setattr(uc, "_deliver", AsyncMock())
    inbound = sg.InboundSlack(
        team_id="T", channel="C1", user="U", text="hi", thread_ts="1.0", selector=None
    )

    await uc._watch_self_posting_turn(svc, "task-1", {"m1"}, inbound)

    uc._deliver.assert_not_awaited()
    uc._set_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_watch_ignores_our_own_user_message(monkeypatch):
    """The event we just sent creates a USER message immediately, so "any new message"
    would always look like success and the watch would never fire."""
    monkeypatch.setattr(sg, "_GOLDEN_REPLY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sg, "_GOLDEN_REPLY_POLL_S", 0.01)
    uc = SlackGatewayUseCase()
    svc = MagicMock()
    svc.get_messages = AsyncMock(return_value=[_Msg("m2", "user", "hi")])
    monkeypatch.setattr(uc, "_set_status", AsyncMock())
    delivered = []
    monkeypatch.setattr(
        uc, "_deliver", AsyncMock(side_effect=lambda i, t: delivered.append(t))
    )
    inbound = sg.InboundSlack(
        team_id="T", channel="C1", user="U", text="hi", thread_ts="1.0", selector=None
    )

    await uc._watch_self_posting_turn(svc, "task-1", {"m1"}, inbound)

    assert len(delivered) == 1, "a user message alone must not count as agent output"


# --- duplicate-config guards -----------------------------------------------


class _FailingSGP(_FakeSGP):
    """Lookup fails. Distinct from 'lookup returned nothing'."""

    def client(self):
        outer = self

        class _Client:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None, params=None):
                raise RuntimeError("sgp unreachable")

            async def post(self, url, headers=None, json=None):
                outer.posts.append({"url": url, "headers": headers, "json": json})

                class _R:
                    status_code, _p = 200, {"id": "should-not-happen"}

                    def json(self):
                        return self._p

                return _R()

        return _Client


@pytest.mark.asyncio
async def test_a_failed_lookup_never_creates_a_duplicate(monkeypatch):
    """A blip must not become a second config with the same name — after that,
    by-name resolution returns whichever the list happens to yield first."""
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    fake = _FailingSGP()
    monkeypatch.setattr(sg.httpx, "AsyncClient", fake.client())

    cid = await SlackGatewayUseCase()._own_config_id(_user_headers("dave"), "u-dave")

    assert cid is None, "unknown state -> degrade this turn, don't create"
    assert fake.posts == [], "must not POST when we don't know if one exists"


@pytest.mark.asyncio
async def test_a_definitively_empty_lookup_does_create(monkeypatch):
    """The other half: [] means 'definitively none', so creating is correct."""
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    fake = _FakeSGP(existing=[], create_id="made-1")
    monkeypatch.setattr(sg.httpx, "AsyncClient", fake.client())

    cid = await SlackGatewayUseCase()._own_config_id(_user_headers("erin"), "u-erin")

    assert cid == "made-1"
    assert len(fake.posts) == 1


def test_duplicate_names_resolve_the_same_way_for_every_worker():
    """Two workers must agree, forever, regardless of edits.

    Ordered on created_at + id, both immutable. updated_at is deliberately ignored:
    editing a duplicate would otherwise MOVE which one is canonical, and workers whose
    caches were populated either side of that edit would serve different configs for
    the same user.
    """
    older = {
        "id": "b-older",
        "name": "slack-agentex-bot",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    newer = {
        "id": "a-newer",
        "name": "slack-agentex-bot",
        "created_at": "2026-09-01T00:00:00",
        "updated_at": "2026-12-31T00:00:00",  # edited most recently
    }
    other = {"id": "x", "name": "something-else", "created_at": "2020-01-01T00:00:00"}

    for order in ([older, newer, other], [newer, other, older], [other, newer, older]):
        assert (
            sg._canonical_named(order, "slack-agentex-bot") == "b-older"
        ), "list order must not change the answer"
    assert sg._canonical_named([older, newer], "absent") is None


# --- concurrent first turns ------------------------------------------------
#
# The deployment runs multiple replicas and the cache is process-local, so two
# first turns for one user can both miss the cache, both see [], and both
# create. What must NOT happen is the two ending up on different configs.


@pytest.mark.asyncio
async def test_concurrent_create_converges_on_one_config(monkeypatch):
    """Worker A creates, then lists and sees B's too. It must adopt the canonical
    pick rather than trusting its own POST, or A and B serve different prompts and
    toolsets for the same user, turn to turn."""
    monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})

    mine = {
        "id": "mine-second",
        "name": sg._USER_CONFIG_NAME,
        "created_at": "2026-09-02T00:00:01",
    }
    theirs = {
        "id": "theirs-first",
        "name": sg._USER_CONFIG_NAME,
        "created_at": "2026-09-02T00:00:00",
    }
    calls = {"gets": 0}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            calls["gets"] += 1
            # First list: empty, so we create. Second (post-create): both exist.
            items = [] if calls["gets"] == 1 else [mine, theirs]

            class _R:
                status_code = 200

                def json(self):
                    return {"items": items}

            return _R()

        async def post(self, url, headers=None, json=None):
            class _R:
                status_code = 200

                def json(self):
                    return {"id": "mine-second"}

            return _R()

    monkeypatch.setattr(sg.httpx, "AsyncClient", _Client)

    got = await SlackGatewayUseCase()._own_config_id(_user_headers("f"), "u-f")

    assert got == "theirs-first", "must adopt the canonical id, not its own creation"
    assert sg._cache_get(("acct1", "u-f", sg._USER_CONFIG_NAME)) == "theirs-first"


@pytest.mark.asyncio
async def test_cache_expires_so_a_divergence_can_heal(monkeypatch):
    """If two workers do end up cached on different ids, entries must expire —
    otherwise they serve different configs until someone restarts a pod."""
    monkeypatch.setattr(sg, "_CONFIG_ID_CACHE", {})
    key = ("acct1", "u-g", sg._USER_CONFIG_NAME)
    sg._cache_put(key, "cfg-a")
    assert sg._cache_get(key) == "cfg-a"

    real_monotonic = sg.time.monotonic
    monkeypatch.setattr(
        sg.time,
        "monotonic",
        lambda: real_monotonic() + sg._CONFIG_ID_CACHE_TTL_S + 1,
    )
    assert sg._cache_get(key) is None, "expired entries must not be served"
    assert key not in sg._CONFIG_ID_CACHE, "and should be evicted"
