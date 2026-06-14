from datetime import date

from app_tracker.utils.timeutil import week_bounds


def test_week_bounds_known_week():
    # 2024-01-03 is a Wednesday.
    start, end = week_bounds(date(2024, 1, 3))
    assert start == date(2024, 1, 1)  # Monday
    assert end == date(2024, 1, 7)    # Sunday


def test_week_bounds_spans_seven_days():
    start, end = week_bounds(date(2024, 6, 14))
    assert (end - start).days == 6
    assert start.weekday() == 0
