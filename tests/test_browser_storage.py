from datetime import date, datetime, timedelta, timezone

import pytest

from app_tracker.browser import reports
from app_tracker.browser.storage import BrowserStorage, split_url
from app_tracker.core.database import DatabaseManager

SID_A = "aaaaaaaa-0000-0000-0000-000000000001"
SID_B = "bbbbbbbb-0000-0000-0000-000000000002"


@pytest.fixture
def db(tmp_path):
    manager = DatabaseManager(tmp_path / "browser.db")
    yield manager
    manager.close()


@pytest.fixture
def storage(db):
    return BrowserStorage(db)


def _now():
    # Midday today, so DATE(start_time) is always today in the reports.
    return datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=12)


def test_split_url_drops_query_and_fragment():
    domain, clean = split_url("https://user:pw@www.Example.com/a/b?token=1#x")
    assert domain == "example.com"
    assert clean == "https://example.com/a/b"


def test_session_is_stored_with_duration(storage, db):
    t0 = _now()
    assert storage.start_session(SID_A, "firefox", "https://github.com/x", "x", t0)
    assert storage.stop_session(SID_A, t0 + timedelta(seconds=90)) == 90
    row = db._fetch_one(
        "SELECT domain, category, duration_seconds FROM browser_activity"
    )
    assert row == ("github.com", "Код / Разработка", 90)


def test_timezone_aware_times_are_accepted(storage):
    t0 = datetime.now(timezone.utc)
    assert storage.start_session(SID_A, "firefox", "https://github.com", "", t0)
    assert storage.stop_session(SID_A, t0 + timedelta(seconds=5)) == 5


def test_short_session_is_dropped(storage, db):
    t0 = _now()
    storage.start_session(SID_A, "firefox", "https://github.com", "", t0)
    assert storage.stop_session(SID_A, t0) == 0
    assert db._fetch_one("SELECT COUNT(*) FROM browser_activity")[0] == 0


def test_starting_a_new_session_closes_the_old_one(storage):
    t0 = _now()
    storage.start_session(SID_A, "firefox", "https://github.com", "", t0)
    storage.start_session(SID_B, "firefox", "https://vk.com", "", t0 + timedelta(seconds=30))
    # A was closed automatically, so stopping it again does nothing.
    assert storage.stop_session(SID_A, t0 + timedelta(seconds=60)) is None


def test_ignored_domains_and_disabled_tracking(storage):
    t0 = _now()
    storage.set_ignored_domains(["bank.kz", " "])
    assert storage.ignored_domains() == ["bank.kz"]
    assert not storage.start_session(SID_A, "firefox", "https://online.bank.kz", "", t0)

    storage.set_enabled(False)
    assert not storage.start_session(SID_B, "firefox", "https://github.com", "", t0)


def test_title_update_changes_category(storage, db):
    t0 = _now()
    storage.start_session(SID_A, "firefox", "https://youtube.com/watch", "Cats", t0)
    assert storage.update_title(SID_A, "Physics Lecture 4")
    assert db._fetch_one("SELECT category FROM browser_activity")[0] == "Учёба"
    assert not storage.update_title("missing-session-id", "x")


def test_open_sessions_are_discarded_on_restart(db):
    first = BrowserStorage(db)
    first.start_session(SID_A, "firefox", "https://github.com", "", _now())
    BrowserStorage(db)  # app restarted
    assert db._fetch_one("SELECT COUNT(*) FROM browser_activity")[0] == 0


def test_reports(storage, db):
    t0 = _now()
    sessions = [
        (SID_A, "https://youtube.com/watch", "Physics Lecture 4", 600),
        (SID_B, "https://youtube.com/watch", "Funny cats", 100),
        ("cccccccc-0000-0000-0000-000000000003", "https://github.com/x", "x", 300),
    ]
    for sid, url, title, seconds in sessions:
        storage.start_session(sid, "firefox", url, title, t0)
        storage.stop_session(sid, t0 + timedelta(seconds=seconds))
        t0 += timedelta(seconds=seconds)

    start, end = reports.period_bounds(1)
    assert reports.total_seconds(db, start, end) == 1000
    assert reports.category_totals(db, start, end) == [
        ("Учёба", 600), ("Код / Разработка", 300), ("Развлечения", 100),
    ]
    sites = reports.domain_totals(db, start, end)
    assert [(s.domain, s.category, s.seconds, s.visits) for s in sites] == [
        ("youtube.com", "Учёба", 700, 2),
        ("github.com", "Код / Разработка", 300, 1),
    ]


def test_period_bounds():
    today = date(2026, 11, 22)
    assert reports.period_bounds(1, today) == (today, today)
    assert reports.period_bounds(7, today) == (date(2026, 11, 16), today)
    assert reports.period_bounds(0, today) == (today, today)


def test_repeated_start_is_ignored_and_restores_after_restart(db):
    # The extension re-sends "start" every minute for the open session.
    t0 = _now()
    first = BrowserStorage(db)
    assert first.start_session(SID_A, "firefox", "https://github.com", "", t0)
    assert not first.start_session(SID_A, "firefox", "https://github.com", "", t0)

    # The app restarts: the open session is dropped, then the next
    # heartbeat brings it back with its original start time.
    second = BrowserStorage(db)
    assert second.start_session(SID_A, "firefox", "https://github.com", "", t0)
    assert second.stop_session(SID_A, t0 + timedelta(minutes=5)) == 300
