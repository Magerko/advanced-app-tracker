from datetime import timedelta

import pytest

from app_tracker.config import (
    SETTING_IDLE_THRESHOLD,
    SETTING_MINIMIZE_TO_TRAY,
    SETTING_PASSWORD_HASH,
)
from app_tracker.core.database import DatabaseManager
from app_tracker.core.productivity import Productivity


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(db_path=tmp_path / "test.db")
    yield manager
    manager.close()


def test_default_idle_threshold_is_seeded(db):
    assert db.get_int(SETTING_IDLE_THRESHOLD, 0) == 60


def test_get_or_create_app_dedups(db):
    first = db.get_or_create_app("Foo", r"C:\Apps\foo.exe")
    second = db.get_or_create_app("Foo", r"C:\Apps\foo.exe")
    other = db.get_or_create_app("Bar", r"C:\Apps\bar.exe")
    assert first == second
    assert other != first
    assert db.get_or_create_app("Foo", "") is None


def test_set_productivity(db):
    app_id = db.get_or_create_app("Foo", r"C:\Apps\foo.exe")
    assert db.set_app_productivity(app_id, Productivity.PRODUCTIVE)
    assert db.get_app_details(app_id)[2] == int(Productivity.PRODUCTIVE)
    assert not db.set_app_productivity(app_id, 99)


def test_usage_log_records_duration(db):
    app_id = db.get_or_create_app("Foo", r"C:\Apps\foo.exe")
    log_id = db.start_usage_log(app_id)
    start = db.get_log_start_time(log_id)
    db.end_usage_log(log_id, start + timedelta(seconds=90))

    summary = db.get_usage_summary()
    assert summary[app_id]["today"] == 90
    assert summary[app_id]["week"] == 90


def test_subsecond_session_is_discarded(db):
    app_id = db.get_or_create_app("Foo", r"C:\Apps\foo.exe")
    log_id = db.start_usage_log(app_id)
    start = db.get_log_start_time(log_id)
    db.end_usage_log(log_id, start + timedelta(milliseconds=400))

    assert db.get_log_start_time(log_id) is None
    assert db.get_usage_summary()[app_id]["today"] == 0


def test_limits_roundtrip(db):
    app_id = db.get_or_create_app("Foo", r"C:\Apps\foo.exe")
    db.set_limit(app_id, 3600, None)
    assert db.get_all_limits()[app_id] == {"daily": 3600, "weekly": None}


def test_text_and_int_settings(db):
    db.set_bool(SETTING_MINIMIZE_TO_TRAY, True)
    assert db.get_bool(SETTING_MINIMIZE_TO_TRAY) is True

    db.set_setting(SETTING_IDLE_THRESHOLD, "123")
    assert db.get_int(SETTING_IDLE_THRESHOLD, 0) == 123

    # only_if_absent must not overwrite an existing value.
    db.set_setting(SETTING_IDLE_THRESHOLD, "999", only_if_absent=True)
    assert db.get_int(SETTING_IDLE_THRESHOLD, 0) == 123


def test_setting_none_deletes(db):
    db.set_bool(SETTING_MINIMIZE_TO_TRAY, True)
    db.set_setting(SETTING_MINIMIZE_TO_TRAY, None)
    assert db.get_setting(SETTING_MINIMIZE_TO_TRAY) is None


def test_password_hash_stored_as_raw_bytes(db):
    db.set_setting(SETTING_PASSWORD_HASH, b"\x00\x01raw")
    assert db.get_setting(SETTING_PASSWORD_HASH) == b"\x00\x01raw"


def test_daily_totals_length(db):
    totals = db.get_daily_totals(num_days=5)
    assert len(totals) == 5
    assert all("date" in row and "seconds" in row for row in totals)


def test_access_after_close_degrades_gracefully(tmp_path):
    manager = DatabaseManager(db_path=tmp_path / "closed.db")
    manager.close()
    # No AttributeError on a closed connection; reads return safe defaults.
    assert manager.get_all_apps() == []
    assert manager.get_setting("anything") is None
    assert manager.get_bool(SETTING_MINIMIZE_TO_TRAY) is False
