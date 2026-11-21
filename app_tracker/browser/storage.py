"""Browser-activity persistence on top of the shared DatabaseManager."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

from app_tracker.browser.categorizer import categorize_url
from app_tracker.config import SETTING_BROWSER_ENABLED, SETTING_BROWSER_IGNORED
from app_tracker.core.database import DatabaseManager

log = logging.getLogger(__name__)

MAX_TITLE = 500
MAX_URL = 2048
MIN_SESSION_SECONDS = 1


def to_local_naive(value: datetime) -> datetime:
    """The app stores local time without tzinfo (see usage_log)."""
    if value.tzinfo is not None:
        value = value.astimezone()
    return value.replace(tzinfo=None)


def split_url(url: str) -> Tuple[str, str]:
    """Return (domain, address without query, fragment or credentials)."""
    parts = urlsplit(url)
    domain = (parts.hostname or "").lower().removeprefix("www.")
    return domain, f"{parts.scheme}://{domain}{parts.path}"


class BrowserStorage:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._create_schema()
        self._discard_open_sessions()

    # --- schema -----------------------------------------------------------

    def _create_schema(self) -> None:
        self._db._execute(
            """
            CREATE TABLE IF NOT EXISTS browser_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                browser TEXT NOT NULL,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                category TEXT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                duration_seconds INTEGER
            )
            """
        )
        self._db._execute(
            "CREATE INDEX IF NOT EXISTS idx_browser_activity_start_time "
            "ON browser_activity(start_time)"
        )

    def _discard_open_sessions(self) -> None:
        # After a crash or restart the real end of an open session is unknown.
        self._db._execute("DELETE FROM browser_activity WHERE end_time IS NULL")

    # --- settings ---------------------------------------------------------

    def is_enabled(self) -> bool:
        return self._db.get_bool(SETTING_BROWSER_ENABLED, True)

    def set_enabled(self, enabled: bool) -> None:
        self._db.set_bool(SETTING_BROWSER_ENABLED, enabled)

    def ignored_domains(self) -> List[str]:
        raw = self._db.get_setting(SETTING_BROWSER_IGNORED, "") or ""
        return [d.strip().lower() for d in str(raw).split(",") if d.strip()]

    def set_ignored_domains(self, domains: List[str]) -> None:
        cleaned = [d.strip().lower() for d in domains if d.strip()]
        self._db.set_setting(SETTING_BROWSER_IGNORED, ",".join(cleaned))

    def is_ignored(self, domain: str) -> bool:
        return any(
            domain == d or domain.endswith("." + d) for d in self.ignored_domains()
        )

    # --- events -----------------------------------------------------------

    def start_session(
        self, session_id: str, browser: str, url: str, title: str, started_at: datetime
    ) -> bool:
        if not self.is_enabled():
            return False
        domain, clean_url = split_url(url)
        if not domain or self.is_ignored(domain):
            return False

        # Only one tab is active at a time: close anything left open
        # (for example after the extension was reloaded).
        self._close_other_sessions(browser, session_id, started_at)

        cur = self._db._execute(
            "INSERT OR IGNORE INTO browser_activity "
            "(session_id, browser, domain, url, title, category, start_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, browser, domain, clean_url[:MAX_URL],
                (title or "")[:MAX_TITLE], categorize_url(url, title),
                to_local_naive(started_at),
            ),
        )
        return bool(cur and cur.rowcount > 0)

    def _close_other_sessions(
        self, browser: str, keep_session_id: str, at: datetime
    ) -> None:
        rows = self._db._fetch_all(
            "SELECT session_id FROM browser_activity "
            "WHERE end_time IS NULL AND browser = ? AND session_id != ?",
            (browser, keep_session_id),
        )
        for (old_id,) in rows:
            self.stop_session(old_id, at)

    def update_title(self, session_id: str, title: str) -> bool:
        row = self._db._fetch_one(
            "SELECT url FROM browser_activity WHERE session_id = ?", (session_id,)
        )
        if not row:
            return False
        title = (title or "")[:MAX_TITLE]
        self._db._execute(
            "UPDATE browser_activity SET title = ?, category = ? WHERE session_id = ?",
            (title, categorize_url(row[0], title), session_id),
        )
        return True

    def stop_session(self, session_id: str, ended_at: datetime) -> Optional[int]:
        row = self._db._fetch_one(
            "SELECT start_time FROM browser_activity "
            "WHERE session_id = ? AND end_time IS NULL",
            (session_id,),
        )
        if not row:
            return None
        end = to_local_naive(ended_at)
        duration = int((end - row[0]).total_seconds())
        if duration >= MIN_SESSION_SECONDS:
            self._db._execute(
                "UPDATE browser_activity SET end_time = ?, duration_seconds = ? "
                "WHERE session_id = ?",
                (end, duration, session_id),
            )
            return duration
        # Same convention as usage_log: drop sub-second blips.
        self._db._execute(
            "DELETE FROM browser_activity WHERE session_id = ?", (session_id,)
        )
        return 0
