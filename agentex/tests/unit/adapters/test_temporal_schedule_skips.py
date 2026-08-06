from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.exceptions import TemporalInvalidArgumentError
from temporalio.client import ScheduleCalendarSpec, ScheduleRange


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


@pytest.mark.unit
def test_extract_one_off_skip_times_can_filter_to_future_times():
    old_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
    future_time = datetime(2026, 7, 11, 15, 0, tzinfo=UTC)
    old_skip = TemporalAdapter._one_off_skip_spec(old_time, None)
    future_skip = TemporalAdapter._one_off_skip_spec(future_time, None)

    assert TemporalAdapter.extract_one_off_skip_times(
        _description(skips=[old_skip, future_skip]),
        after=datetime(2026, 7, 10, 15, 0, tzinfo=UTC),
    ) == [future_time]


@pytest.mark.unit
def test_without_past_one_off_skips_preserves_broad_skip_specs():
    old_time = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
    future_time = datetime(2026, 7, 11, 15, 0, tzinfo=UTC)
    old_skip = TemporalAdapter._one_off_skip_spec(old_time, None)
    future_skip = TemporalAdapter._one_off_skip_spec(future_time, None)
    weekend_skip = ScheduleCalendarSpec(day_of_week=[ScheduleRange(start=0, end=1)])

    assert TemporalAdapter._without_past_one_off_skips(
        [old_skip, future_skip, weekend_skip],
        None,
        now=datetime(2026, 7, 10, 15, 0, tzinfo=UTC),
    ) == [future_skip, weekend_skip]


@pytest.mark.unit
def test_contains_instant_matches_equivalent_timezone_instants():
    target = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
    same_instant = datetime(2026, 7, 9, 11, 0, tzinfo=ZoneInfo("America/New_York"))

    assert TemporalAdapter._contains_instant(target, [same_instant])


@pytest.mark.unit
def test_validate_future_scheduled_time_rejects_past_time():
    with pytest.raises(TemporalInvalidArgumentError):
        TemporalAdapter._validate_future_scheduled_time(
            datetime(2026, 7, 9, 15, 0, tzinfo=UTC),
            now=datetime(2026, 7, 10, 15, 0, tzinfo=UTC),
            operation="skip",
        )
