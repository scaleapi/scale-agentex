"""Unit tests for the Slack gateway — everything that does NOT require a real Slack
app: signature verification, event normalization, the handle_slack_event control flow
(challenge / dev-skip / drop / ack), and that _run_turn dispatches correctly (ACP
mocked). No running stack, no golden_agent, no Slack.
"""

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
    async def test_unmatched_selector_falls_back_to_default_config(self):
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
        assert target == Target("golden-agent", config_id=sg._DEFAULT_CONFIG_ID)
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
            Target("golden-agent", config_id=sg._DEFAULT_CONFIG_ID),
            inbound,
            "hello",
            None,
            {},
        )

        assert acp.handle_rpc_request.await_count == 2
        first, second = acp.handle_rpc_request.await_args_list
        assert first.kwargs["method"] == AgentRPCMethod.TASK_CREATE
        assert first.kwargs["params"].name == "slack:1700000000.000100"
        # First turn passes the default agent_config id so golden-agent resolves its
        # full turn config (prompt/model/tools) from it.
        assert first.kwargs["params"].params["config_id"] == sg._DEFAULT_CONFIG_ID
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
        assert sg._CONFIG_ID_CACHE[("acct1", "my-config")] == "cfg-123"  # cached

    @pytest.mark.asyncio
    async def test_resolve_config_id_none_without_base_or_key(self, monkeypatch):
        uc = SlackGatewayUseCase()
        monkeypatch.setattr(sg, "_SGP_BASE_URL", "")
        assert await uc._resolve_config_id("x", {"x-api-key": "k"}) is None  # no base
        monkeypatch.setattr(sg, "_SGP_BASE_URL", "https://sgp.example")
        assert await uc._resolve_config_id("x", {}) is None  # no acting key


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
