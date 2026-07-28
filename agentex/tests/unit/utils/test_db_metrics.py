"""Tests for the InstrumentedAsyncAdaptedQueuePool connection-acquisition metrics.

These three series (wait_time / pending_requests / timeouts) can't be sourced
from SQLAlchemy's checkout/checkin events, so they're emitted from a connect()
override. The contract under test:

  * unattached (OTel disabled) -> connect() is a pure passthrough,
  * success -> pending +1 then -1, wait_time recorded once, no timeout,
  * pool timeout -> timeout counted, pending balanced, wait_time NOT recorded,
    and the original error still propagates,
  * recreate() carries the instruments forward so metrics survive a dispose.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.pool import AsyncAdaptedQueuePool
from src.utils import db_metrics
from src.utils.db_metrics import (
    InstrumentedAsyncAdaptedQueuePool,
    _PoolWaitInstruments,
)


def _make_pool() -> InstrumentedAsyncAdaptedQueuePool:
    # A creator that is never invoked: super().connect() is patched in every
    # test that exercises acquisition, so no real DBAPI connection is made.
    return InstrumentedAsyncAdaptedQueuePool(lambda: None, pool_size=1, max_overflow=0)


def _mock_instruments() -> tuple[_PoolWaitInstruments, dict]:
    attributes = {"db.client.connection.pool.name": "main"}
    instruments = _PoolWaitInstruments(
        wait_time=MagicMock(),
        pending_requests=MagicMock(),
        timeouts=MagicMock(),
        attributes=attributes,
    )
    return instruments, attributes


@pytest.mark.unit
def test_connect_is_passthrough_when_no_instruments_attached():
    pool = _make_pool()
    sentinel = object()
    with patch.object(
        AsyncAdaptedQueuePool, "connect", return_value=sentinel
    ) as super_connect:
        assert pool.connect() is sentinel
    super_connect.assert_called_once()


@pytest.mark.unit
def test_connect_success_records_wait_time_and_balances_pending():
    pool = _make_pool()
    instruments, attributes = _mock_instruments()
    pool.attach_wait_instruments(instruments)

    sentinel = object()
    with patch.object(AsyncAdaptedQueuePool, "connect", return_value=sentinel):
        assert pool.connect() is sentinel

    # Joined the queue, then left it — net zero.
    assert instruments.pending_requests.add.call_args_list == [
        call(1, attributes),
        call(-1, attributes),
    ]
    instruments.wait_time.record.assert_called_once()
    recorded_value, recorded_attrs = instruments.wait_time.record.call_args.args
    assert recorded_value >= 0
    assert recorded_attrs is attributes
    instruments.timeouts.add.assert_not_called()


@pytest.mark.unit
def test_connect_timeout_counts_timeout_and_skips_wait_time():
    pool = _make_pool()
    instruments, attributes = _mock_instruments()
    pool.attach_wait_instruments(instruments)

    boom = SQLAlchemyTimeoutError("QueuePool limit reached")
    with patch.object(AsyncAdaptedQueuePool, "connect", side_effect=boom):
        with pytest.raises(SQLAlchemyTimeoutError):
            pool.connect()

    instruments.timeouts.add.assert_called_once_with(1, attributes)
    # A timed-out acquisition obtained no connection, so no wait_time sample.
    instruments.wait_time.record.assert_not_called()
    # pending is still balanced even though acquisition failed.
    assert instruments.pending_requests.add.call_args_list == [
        call(1, attributes),
        call(-1, attributes),
    ]


@pytest.mark.unit
def test_connect_non_timeout_error_balances_pending_without_counting_timeout():
    pool = _make_pool()
    instruments, attributes = _mock_instruments()
    pool.attach_wait_instruments(instruments)

    with patch.object(
        AsyncAdaptedQueuePool, "connect", side_effect=RuntimeError("driver blew up")
    ):
        with pytest.raises(RuntimeError):
            pool.connect()

    instruments.timeouts.add.assert_not_called()
    instruments.wait_time.record.assert_not_called()
    assert instruments.pending_requests.add.call_args_list == [
        call(1, attributes),
        call(-1, attributes),
    ]


@pytest.mark.unit
def test_recreate_carries_instruments_forward():
    pool = _make_pool()
    instruments, _ = _mock_instruments()
    pool.attach_wait_instruments(instruments)

    new_pool = pool.recreate()
    assert isinstance(new_pool, InstrumentedAsyncAdaptedQueuePool)
    assert new_pool._wait_instruments is instruments


@pytest.mark.unit
def test_register_engine_attaches_instruments_to_pool():
    # End-to-end wiring: PostgresPoolMetrics should hand its instruments to an
    # InstrumentedAsyncAdaptedQueuePool when OTel is enabled.
    pool = _make_pool()
    fake_engine = MagicMock()
    fake_engine.sync_engine.pool = pool

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(db_metrics, "get_meter", return_value=MagicMock())
        )
        # Don't register real SQLAlchemy event listeners against the mock engine.
        stack.enter_context(
            patch.object(db_metrics.PostgresPoolMetrics, "_register_pool_events")
        )
        db_metrics.PostgresPoolMetrics(
            engine=fake_engine,
            pool_name="main",
            db_url="postgresql://user:pass@localhost:5432/agentex",
            environment="test",
        )

    assert pool._wait_instruments is not None
    assert pool._wait_instruments.attributes["db.client.connection.pool.name"] == "main"
