import os

from app_tracker.utils.formatting import (
    format_duration,
    friendly_app_name,
    parse_time_input,
)


def test_format_duration_none():
    assert format_duration(None) == "N/A"


def test_format_duration_ranges():
    assert format_duration(0) == "0с"
    assert format_duration(59) == "59с"
    assert format_duration(60) == "1м 0с"
    assert format_duration(150) == "2м 30с"
    assert format_duration(3661) == "1ч 1м"


def test_format_duration_clamps_negative():
    assert format_duration(-5) == "0с"


def test_parse_time_input_empty_is_zero():
    assert parse_time_input("") == 0


def test_parse_time_input_units():
    assert parse_time_input("1ч 30м") == 5400
    assert parse_time_input("45m") == 2700
    assert parse_time_input("2h") == 7200
    assert parse_time_input("90") == 90  # bare number is seconds


def test_parse_time_input_invalid():
    assert parse_time_input("abc") is None
    assert parse_time_input("1ч xyz") is None


def test_friendly_app_name():
    path = os.path.join("C:", "Apps", "google-chrome.exe")
    assert friendly_app_name(None, path) == "Google Chrome"
    assert friendly_app_name("proc", None) == "proc"
    assert friendly_app_name(None, None) == "Неизвестно"
