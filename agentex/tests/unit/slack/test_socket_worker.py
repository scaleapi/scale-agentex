"""Unit tests for the production Socket Mode worker's non-Slack logic: event
dedup (at-least-once → skip redelivered events) and event dispatch. slack_sdk is
imported lazily in the worker's runtime methods, so these run without it."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.slack.socket_worker import SocketWorker


@pytest.mark.unit
class TestDedup:
    @pytest.mark.asyncio
    async def test_first_time_is_not_duplicate(self):
        w = SocketWorker()
        w._redis = MagicMock()
        w._redis.set = AsyncMock(return_value=True)  # NX set succeeded → first time
        assert await w._already_processed("Ev1") is False
        w._redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_time_is_duplicate(self):
        w = SocketWorker()
        w._redis = MagicMock()
        w._redis.set = AsyncMock(return_value=None)  # key already existed
        assert await w._already_processed("Ev1") is True

    @pytest.mark.asyncio
    async def test_no_redis_fails_open(self):
        w = SocketWorker()
        w._redis = None
        assert await w._already_processed("Ev1") is False

    @pytest.mark.asyncio
    async def test_no_event_id_fails_open(self):
        w = SocketWorker()
        w._redis = MagicMock()
        w._redis.set = AsyncMock()
        assert await w._already_processed(None) is False
        w._redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_error_fails_open(self):
        w = SocketWorker()
        w._redis = MagicMock()
        w._redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
        assert await w._already_processed("Ev1") is False  # never blocks a turn


_EVENT = {
    "event_id": "Ev1",
    "team_id": "T",
    "api_app_id": "A0",
    "event": {
        "type": "app_mention",
        "user": "U",
        "text": "<@U> hi",
        "channel": "C",
        "ts": "1",
    },
}


@pytest.mark.unit
class TestHandleEvent:
    @pytest.mark.asyncio
    async def test_duplicate_skips_dispatch(self, monkeypatch):
        w = SocketWorker()
        monkeypatch.setattr(w, "_already_processed", AsyncMock(return_value=True))
        run_turn = AsyncMock()
        monkeypatch.setattr(w._gateway, "_run_turn", run_turn)

        await w._handle_event(_EVENT)

        run_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_new_event_dispatches(self, monkeypatch):
        w = SocketWorker()
        monkeypatch.setattr(w, "_already_processed", AsyncMock(return_value=False))
        run_turn = AsyncMock()
        monkeypatch.setattr(w._gateway, "_run_turn", run_turn)

        await w._handle_event(_EVENT)

        run_turn.assert_awaited_once()
        inbound = run_turn.await_args.args[0]
        assert inbound.channel == "C"
        assert inbound.text == "hi"

    @pytest.mark.asyncio
    async def test_ignored_event_does_not_dispatch(self, monkeypatch):
        w = SocketWorker()
        monkeypatch.setattr(w, "_already_processed", AsyncMock(return_value=False))
        run_turn = AsyncMock()
        monkeypatch.setattr(w._gateway, "_run_turn", run_turn)

        # bot_id set → normalize() returns None (our own message) → no dispatch
        await w._handle_event(
            {"event_id": "Ev9", "event": {"type": "app_mention", "bot_id": "B1"}}
        )

        run_turn.assert_not_awaited()


@pytest.mark.unit
class TestConnectedFlag:
    def test_no_client_is_disconnected(self):
        assert SocketWorker()._connected() is False

    def test_uses_client_is_connected(self):
        w = SocketWorker()
        w._client = MagicMock()
        w._client.is_connected = MagicMock(return_value=True)
        assert w._connected() is True
        w._client.is_connected.return_value = False
        assert w._connected() is False
