"""Background tracking worker.

Lives on its own :class:`QThread`. Every tick it determines the foreground
application, maintains the open usage-log row, recomputes today/week totals
and checks configured limits. Communication with the UI is exclusively via
signals; UI -> worker calls go through ``@pyqtSlot`` methods invoked with
``QMetaObject.invokeMethod`` (which is why the slots are decorated).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app_tracker.config import (
    DEFAULT_IDLE_THRESHOLD_SECONDS,
    IGNORED_EXECUTABLES,
    SETTING_IDLE_THRESHOLD,
    SETTING_TERMINATE_ON_LIMIT,
    UPDATE_INTERVAL_MS,
)
from app_tracker.core.database import DatabaseManager
from app_tracker.core.idle_detector import IdleDetector
from app_tracker.core.productivity import Productivity
from app_tracker.platform_support import get_active_window_info
from app_tracker.utils import friendly_app_name

log = logging.getLogger(__name__)

#: Don't re-issue a terminate request for the same PID more often than this.
_TERMINATE_COOLDOWN_S = 30
#: Warn when usage reaches this fraction of a limit.
_WARN_FRACTION = 0.9


class TrackerWorker(QObject):
    # usage_summary, limits, totals
    usageUpdated = pyqtSignal(dict, dict, dict)
    # app_id, app_name, kind ("daily"/"daily-warn"/"weekly"/"weekly-warn"), usage, limit
    limitWarning = pyqtSignal(int, str, str, int, int)
    statusChanged = pyqtSignal(str)
    requestTerminateApp = pyqtSignal(int)

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__()
        self.db = db_manager

        self._running = False
        self._paused = False
        self._is_idle = False

        self.current_log_id: Optional[int] = None
        self.current_app_id: Optional[int] = None
        self._last_app_path: Optional[str] = None
        self._active_pid: Optional[int] = None

        self.usage_summary: Dict[int, Dict[str, Any]] = {}
        self.limits: Dict[int, Dict[str, Optional[int]]] = {}
        self.totals = self._empty_totals()
        self._last_status = "Инициализация…"
        self._terminate_requested_at: Dict[int, float] = {}

        self._terminate_on_limit = self.db.get_bool(SETTING_TERMINATE_ON_LIMIT)
        threshold = self.db.get_int(SETTING_IDLE_THRESHOLD, DEFAULT_IDLE_THRESHOLD_SECONDS)
        # Parent the detector to the worker so it migrates with us when the
        # worker is moved to its QThread (otherwise its QTimer would live on
        # the main thread and Qt would warn about cross-thread timer access).
        self.idle_detector = IdleDetector(threshold, parent=self)
        self.idle_detector.idle_changed.connect(self._on_idle_changed)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    @staticmethod
    def _empty_totals() -> Dict[str, int]:
        return {"today": 0, "week": 0, "prod_today": 0, "prod_week": 0,
                "unprod_today": 0, "unprod_week": 0}

    # -- control slots (invoked from the UI thread) ---------------------------
    @pyqtSlot()
    def start_tracking(self) -> None:
        if self._running:
            return
        self._running = True
        self._paused = False
        self.idle_detector.start()
        self._timer.start(UPDATE_INTERVAL_MS)
        self._emit_status("Отслеживание активно")
        log.info("Tracking started.")

    @pyqtSlot()
    def stop_tracking(self) -> None:
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self.idle_detector.stop()
        self._end_current_log()
        self._emit_status("Остановлено")
        log.info("Tracking stopped.")

    @pyqtSlot()
    def pause_tracking(self) -> None:
        if not self._running or self._paused:
            return
        self._paused = True
        self._end_current_log()
        self._emit_status("Приостановлено")

    @pyqtSlot()
    def resume_tracking(self) -> None:
        if not self._running or not self._paused:
            return
        self._paused = False
        self._emit_status("Отслеживание активно")

    @pyqtSlot(int)
    def set_idle_threshold(self, seconds: int) -> None:
        self.idle_detector.set_threshold(seconds)
        self._emit_status(self._status_text())

    @pyqtSlot()
    def reload_settings(self) -> None:
        self._terminate_on_limit = self.db.get_bool(SETTING_TERMINATE_ON_LIMIT)
        log.info("Settings reloaded (terminate_on_limit=%s).", self._terminate_on_limit)

    @property
    def is_paused(self) -> bool:
        return self._paused

    # -- idle handling --------------------------------------------------------
    def _on_idle_changed(self, is_idle: bool) -> None:
        if self._is_idle == is_idle:
            return
        self._is_idle = is_idle
        log.debug("Idle state -> %s", "IDLE" if is_idle else "ACTIVE")
        if is_idle:
            self._end_current_log()
        self._emit_status(self._status_text())

    # -- core loop ------------------------------------------------------------
    def _tick(self) -> None:
        if not self._running or self._paused or self._is_idle:
            if self.current_log_id is not None:
                self._end_current_log()
            self._emit_status(self._status_text())
            return

        path, name, pid = self._resolve_foreground_app()
        if path != self._last_app_path:
            self._switch_app(path, name, pid)

        self._refresh_summary()
        self._emit_status(self._status_text())

    def _resolve_foreground_app(self):
        info = get_active_window_info()
        if info is None:
            return None, None, None

        if info.executable_path:
            base = os.path.basename(info.executable_path).lower()
            if base in IGNORED_EXECUTABLES:
                return None, None, None
            path = os.path.normpath(info.executable_path)
            name = friendly_app_name(info.process_name, path)
            return path, name, info.pid

        if info.window_title:  # fallback: identify by window title only
            return f"title::{info.window_title}", info.window_title, info.pid
        return None, None, None

    def _switch_app(self, path, name, pid) -> None:
        self._end_current_log()
        if not (path and name):
            return
        app_id = self.db.get_or_create_app(name, path)
        if app_id is None:
            return
        self.current_log_id = self.db.start_usage_log(app_id)
        self.current_app_id = app_id
        self._last_app_path = path
        self._active_pid = pid

    def _end_current_log(self) -> None:
        log_id = self.current_log_id
        self.current_log_id = None
        self.current_app_id = None
        self._last_app_path = None
        self._active_pid = None
        if log_id is not None:
            self.db.end_usage_log(log_id)

    # -- summary / limits -----------------------------------------------------
    def _refresh_summary(self) -> None:
        self.usage_summary = self.db.get_usage_summary()
        self.limits = self.db.get_all_limits()

        # Add the seconds elapsed in the still-open session to "*_display".
        live_seconds = self._current_session_seconds()
        if self.current_app_id is not None:
            entry = self.usage_summary.setdefault(
                self.current_app_id, self._summary_stub(self.current_app_id)
            )
            entry["today_display"] = entry.get("today", 0) + live_seconds
            entry["week_display"] = entry.get("week", 0) + live_seconds

        self.totals = self._empty_totals()
        for app_id, data in self.usage_summary.items():
            today = data.get("today_display", data.get("today", 0))
            week = data.get("week_display", data.get("week", 0))
            prod = data.get("prod", Productivity.UNKNOWN)
            self.totals["today"] += today
            self.totals["week"] += week
            if prod == Productivity.PRODUCTIVE:
                self.totals["prod_today"] += today
                self.totals["prod_week"] += week
            elif prod == Productivity.UNPRODUCTIVE:
                self.totals["unprod_today"] += today
                self.totals["unprod_week"] += week
            self._check_limits(app_id, data.get("name", "?"), today, week)

        self.usageUpdated.emit(self.usage_summary, self.limits, self.totals)

    def _current_session_seconds(self) -> int:
        if self.current_log_id is None:
            return 0
        start = self.db.get_log_start_time(self.current_log_id)
        if start is None:
            return 0
        return max(0, int((datetime.now() - start).total_seconds()))

    def _summary_stub(self, app_id: int) -> Dict[str, Any]:
        details = self.db.get_app_details(app_id)
        if details:
            name, path, prod = details
            return {"name": name, "path": path, "prod": Productivity.from_value(prod),
                    "today": 0, "week": 0}
        return {"name": "?", "path": "?", "prod": Productivity.UNKNOWN, "today": 0, "week": 0}

    def _check_limits(self, app_id: int, name: str, today: int, week: int) -> None:
        limit = self.limits.get(app_id)
        if not limit:
            return

        exceeded = False
        daily = limit.get("daily")
        if daily and daily > 0:
            if today >= daily:
                self.limitWarning.emit(app_id, name, "daily", today, daily)
                exceeded = True
            elif today >= daily * _WARN_FRACTION:
                self.limitWarning.emit(app_id, name, "daily-warn", today, daily)

        weekly = limit.get("weekly")
        if not exceeded and weekly and weekly > 0:
            if week >= weekly:
                self.limitWarning.emit(app_id, name, "weekly", week, weekly)
                exceeded = True
            elif week >= weekly * _WARN_FRACTION:
                self.limitWarning.emit(app_id, name, "weekly-warn", week, weekly)

        if exceeded and self._terminate_on_limit:
            self._maybe_terminate(app_id, name)

    def _maybe_terminate(self, app_id: int, name: str) -> None:
        if app_id != self.current_app_id or self._active_pid is None:
            return
        pid = self._active_pid
        now = time.monotonic()
        last = self._terminate_requested_at.get(pid, 0.0)
        if now - last < _TERMINATE_COOLDOWN_S:
            return  # already asked recently; don't spam every tick
        self._terminate_requested_at[pid] = now
        log.info("Limit exceeded for active app '%s' (PID %s); requesting terminate.", name, pid)
        self.requestTerminateApp.emit(pid)

    # -- status ---------------------------------------------------------------
    def _status_text(self) -> str:
        if not self._running:
            return "Остановлено"
        if self._paused:
            return "Приостановлено"
        if self._is_idle:
            return f"Неактивен ({self.db.get_int(SETTING_IDLE_THRESHOLD, DEFAULT_IDLE_THRESHOLD_SECONDS)}с)"
        if self.current_app_id is not None:
            data = self.usage_summary.get(self.current_app_id)
            if data and data.get("name"):
                return f"Активно: {data['name']}"
        return self._last_status or "Отслеживание активно"

    def _emit_status(self, text: str) -> None:
        if text != self._last_status:
            self._last_status = text
            self.statusChanged.emit(text)
