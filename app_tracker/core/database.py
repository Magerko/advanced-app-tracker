"""SQLite persistence layer.

A single :class:`DatabaseManager` instance is created in ``app.py`` and passed
explicitly to everything that needs it (dependency injection). One connection
is shared between the UI thread and the tracker thread; every access is
serialised through an internal lock, which is safe for this workload.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app_tracker.config import (
    DATE_FORMAT,
    DEFAULT_IDLE_THRESHOLD_SECONDS,
    SETTING_IDLE_THRESHOLD,
    TEXT_SETTING_KEYS,
)
from app_tracker.core.productivity import Productivity
from app_tracker.paths import database_path
from app_tracker.utils import week_bounds

log = logging.getLogger(__name__)

Row = Tuple[Any, ...]


class DatabaseManager:
    """Thread-safe wrapper around the application's SQLite database."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = str(db_path) if db_path is not None else str(database_path())
        self._lock = RLock()
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_schema()
        log.info("Database ready at %s", self.db_path)

    # -- connection / schema --------------------------------------------------
    def _connect(self) -> None:
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")

    def _create_schema(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    executable_path TEXT UNIQUE NOT NULL,
                    productivity INTEGER NOT NULL DEFAULT {int(Productivity.UNKNOWN)}
                );

                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    FOREIGN KEY (app_id) REFERENCES applications (id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_usage_log_start_time ON usage_log(start_time);
                CREATE INDEX IF NOT EXISTS idx_usage_log_app_id ON usage_log(app_id);

                CREATE TABLE IF NOT EXISTS limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id INTEGER UNIQUE NOT NULL,
                    daily_limit_seconds INTEGER,
                    weekly_limit_seconds INTEGER,
                    FOREIGN KEY (app_id) REFERENCES applications (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value BLOB NOT NULL
                );
                """
            )
            self.conn.commit()
            self.set_setting(
                SETTING_IDLE_THRESHOLD,
                str(DEFAULT_IDLE_THRESHOLD_SECONDS),
                only_if_absent=True,
            )

    # -- low-level query helpers ---------------------------------------------
    def _execute(self, query: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Cursor]:
        with self._lock:
            try:
                cur = self.conn.cursor()
                cur.execute(query, params)
                self.conn.commit()
                return cur
            except sqlite3.Error as exc:
                log.error("DB write failed: %s | query=%s", exc, query)
                try:
                    self.conn.rollback()
                except sqlite3.Error:
                    pass
                return None

    def _fetch_one(self, query: str, params: Sequence[Any] = ()) -> Optional[Row]:
        with self._lock:
            try:
                cur = self.conn.cursor()
                cur.execute(query, params)
                return cur.fetchone()
            except sqlite3.Error as exc:
                log.error("DB read failed: %s | query=%s", exc, query)
                return None

    def _fetch_all(self, query: str, params: Sequence[Any] = ()) -> List[Row]:
        with self._lock:
            try:
                cur = self.conn.cursor()
                cur.execute(query, params)
                return cur.fetchall()
            except sqlite3.Error as exc:
                log.error("DB read failed: %s | query=%s", exc, query)
                return []

    # -- applications ---------------------------------------------------------
    def get_or_create_app(
        self, name: str, executable_path: str,
        productivity: Productivity = Productivity.UNKNOWN,
    ) -> Optional[int]:
        if not executable_path:
            return None
        norm_path = os.path.normpath(executable_path)
        row = self._fetch_one(
            "SELECT id FROM applications WHERE executable_path = ?", (norm_path,)
        )
        if row:
            return row[0]
        app_name = name or os.path.basename(norm_path)
        cur = self._execute(
            "INSERT INTO applications (name, executable_path, productivity) VALUES (?, ?, ?)",
            (app_name, norm_path, int(productivity)),
        )
        return cur.lastrowid if cur else None

    def set_app_productivity(self, app_id: int, productivity: Productivity) -> bool:
        if int(productivity) not in (p.value for p in Productivity):
            return False
        return self._execute(
            "UPDATE applications SET productivity = ? WHERE id = ?",
            (int(productivity), app_id),
        ) is not None

    def get_app_details(self, app_id: int) -> Optional[Row]:
        return self._fetch_one(
            "SELECT name, executable_path, productivity FROM applications WHERE id = ?",
            (app_id,),
        )

    def get_all_apps(self) -> List[Row]:
        return self._fetch_all(
            "SELECT id, name, executable_path, productivity FROM applications ORDER BY name ASC"
        )

    # -- usage log ------------------------------------------------------------
    def start_usage_log(self, app_id: int) -> Optional[int]:
        if not app_id:
            return None
        cur = self._execute(
            "INSERT INTO usage_log (app_id, start_time) VALUES (?, ?)",
            (app_id, datetime.now()),
        )
        return cur.lastrowid if cur else None

    def end_usage_log(self, log_id: int, end_time: Optional[datetime] = None) -> None:
        if not log_id:
            return
        row = self._fetch_one(
            "SELECT start_time FROM usage_log WHERE id = ? AND end_time IS NULL",
            (log_id,),
        )
        if not row:
            return
        start_time: datetime = row[0]
        end_time = end_time or datetime.now()
        duration = int((end_time - start_time).total_seconds())
        if duration >= 1:
            self._execute(
                "UPDATE usage_log SET end_time = ?, duration_seconds = ? WHERE id = ?",
                (end_time, duration, log_id),
            )
        else:
            # Discard sub-second blips so they do not clutter the log.
            self._execute("DELETE FROM usage_log WHERE id = ?", (log_id,))

    def get_log_start_time(self, log_id: int) -> Optional[datetime]:
        row = self._fetch_one(
            "SELECT start_time FROM usage_log WHERE id = ?", (log_id,)
        )
        return row[0] if row and isinstance(row[0], datetime) else None

    # -- summaries / reports --------------------------------------------------
    def get_usage_summary(self) -> Dict[int, Dict[str, Any]]:
        """Per-application totals for today and the current week."""
        today = date.today()
        week_start, _ = week_bounds(today)

        summary: Dict[int, Dict[str, Any]] = {}
        for app_id, name, path, prod in self.get_all_apps():
            summary[app_id] = {
                "name": name, "path": path,
                "prod": Productivity.from_value(prod),
                "today": 0, "week": 0,
            }

        q = (
            "SELECT app_id, SUM(duration_seconds) FROM usage_log "
            "WHERE DATE(start_time) {cmp} DATE(?) AND duration_seconds > 0 GROUP BY app_id"
        )
        for app_id, total in self._fetch_all(q.format(cmp="="), (today,)):
            if app_id in summary:
                summary[app_id]["today"] = total or 0
        for app_id, total in self._fetch_all(q.format(cmp=">="), (week_start,)):
            if app_id in summary:
                summary[app_id]["week"] = total or 0
        return summary

    def get_history(self, start_date: date, end_date: date) -> List[Row]:
        return self._fetch_all(
            """
            SELECT a.name, a.executable_path, a.productivity,
                   DATE(u.start_time) AS usage_date, SUM(u.duration_seconds) AS total_seconds
            FROM usage_log u JOIN applications a ON u.app_id = a.id
            WHERE DATE(u.start_time) BETWEEN DATE(?) AND DATE(?) AND u.duration_seconds > 0
            GROUP BY a.id, usage_date ORDER BY usage_date DESC, a.name ASC
            """,
            (start_date, end_date),
        )

    def get_pie_data(self, start_date: date, end_date: date) -> List[Row]:
        return self._fetch_all(
            """
            SELECT a.name, SUM(u.duration_seconds) AS total_seconds
            FROM usage_log u JOIN applications a ON u.app_id = a.id
            WHERE DATE(u.start_time) BETWEEN DATE(?) AND DATE(?) AND u.duration_seconds > 0
            GROUP BY a.id ORDER BY total_seconds DESC
            """,
            (start_date, end_date),
        )

    def get_daily_totals(self, num_days: int = 7) -> List[Dict[str, Any]]:
        end_date = date.today()
        start_date = end_date - timedelta(days=num_days - 1)
        rows = self._fetch_all(
            """
            SELECT DATE(start_time) AS usage_date, SUM(duration_seconds) AS total_seconds
            FROM usage_log
            WHERE DATE(start_time) BETWEEN DATE(?) AND DATE(?) AND duration_seconds > 0
            GROUP BY usage_date ORDER BY usage_date ASC
            """,
            (start_date, end_date),
        )
        by_date = {row[0]: row[1] for row in rows}
        result = []
        for i in range(num_days):
            day = start_date + timedelta(days=i)
            result.append({"date": day, "seconds": by_date.get(day.strftime(DATE_FORMAT), 0)})
        return result

    # -- limits ---------------------------------------------------------------
    def get_all_limits(self) -> Dict[int, Dict[str, Optional[int]]]:
        rows = self._fetch_all(
            "SELECT app_id, daily_limit_seconds, weekly_limit_seconds FROM limits"
        )
        return {row[0]: {"daily": row[1], "weekly": row[2]} for row in rows}

    def set_limit(self, app_id: int, daily: Optional[int], weekly: Optional[int]) -> None:
        self._execute(
            "INSERT OR REPLACE INTO limits (app_id, daily_limit_seconds, weekly_limit_seconds) "
            "VALUES (?, ?, ?)",
            (
                app_id,
                int(daily) if daily is not None else None,
                int(weekly) if weekly is not None else None,
            ),
        )

    # -- settings -------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        if not row:
            return default
        value = row[0]
        if key in TEXT_SETTING_KEYS:
            try:
                return value.decode("utf-8") if isinstance(value, bytes) else str(value)
            except (UnicodeDecodeError, AttributeError):
                return default
        return value  # raw bytes (e.g. password hash)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get_setting(key, str(default))
        return str(value).strip().lower() == "true"

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self.get_setting(key, default))
        except (ValueError, TypeError):
            return default

    def set_setting(self, key: str, value: Any, *, only_if_absent: bool = False) -> None:
        if value is None:
            self._execute("DELETE FROM settings WHERE key = ?", (key,))
            return
        encoded = value.encode("utf-8") if isinstance(value, str) else value
        verb = "INSERT OR IGNORE" if only_if_absent else "INSERT OR REPLACE"
        self._execute(
            f"{verb} INTO settings (key, value) VALUES (?, ?)", (key, encoded)
        )

    def set_bool(self, key: str, value: bool) -> None:
        self.set_setting(key, str(bool(value)))

    # -- lifecycle ------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            if self.conn is not None:
                log.info("Closing database connection.")
                self.conn.close()
                self.conn = None
