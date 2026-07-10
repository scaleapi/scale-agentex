from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from src.adapters.temporal.adapter_temporal import TemporalAdapter


def _description(*, skips, time_zone_name=None):
    return SimpleNamespace(
        schedule=SimpleNamespace(
            spec=SimpleNamespace(skip=skips, time_zone_name=time_zone_name)
        )
    )


@pytest.mark.unit
def test_one_off_skip_round_trips_utc_time():
    scheduled_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)

    skip = TemporalAdapter._one_off_skip_spec(scheduled_time, None)

    assert TemporalAdapter.extract_one_off_skip_times(_description(skips=[skip])) == [
        scheduled_time
    ]


@pytest.mark.unit
def test_one_off_skip_round_trips_named_timezone_to_utc():
    scheduled_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)

    skip = TemporalAdapter._one_off_skip_spec(scheduled_time, "America/New_York")

    assert TemporalAdapter.extract_one_off_skip_times(
        _description(skips=[skip], time_zone_name="America/New_York")
    ) == [scheduled_time]


@pytest.mark.unit
def test_same_one_off_skip_matches_equivalent_instants_in_schedule_timezone():
    scheduled_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
    same_local_time = datetime(2026, 7, 9, 11, 0, tzinfo=ZoneInfo("America/New_York"))

    left = TemporalAdapter._one_off_skip_spec(scheduled_time, "America/New_York")
    right = TemporalAdapter._one_off_skip_spec(same_local_time, "America/New_York")

    assert TemporalAdapter._same_one_off_skip(left, right)
