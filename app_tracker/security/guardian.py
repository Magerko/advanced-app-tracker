"""The guardian: an opt-in anti-kill watchdog.

A small helper process watches the main app's PID and relaunches it if it dies
without first writing a clean-shutdown signal. The in-app side here manages that
helper; the watching loop lives in guardian_helper.py.

A clean exit is always honoured, PID reuse is guarded by process create time,
and a relaunch back-off prevents crash-loops.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Optional

import psutil
from PyQt6.QtCore import QObject, QTimer

from app_tracker.config import WATCHDOG_CHECK_INTERVAL_MS
from app_tracker.paths import guardian_signal_path, project_root

log = logging.getLogger(__name__)


class Guardian(QObject):
    """Manages the guardian helper subprocess from inside the main app."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._helper: Optional[subprocess.Popen] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._ensure_alive)
        self._stopping = False

    def start(self) -> None:
        self._stopping = False
        signal_file = guardian_signal_path()
        try:
            if signal_file.exists():
                signal_file.unlink()
        except OSError as exc:
            log.warning("Could not clear stale guardian signal: %s", exc)
        self._spawn_helper()
        self._timer.start(WATCHDOG_CHECK_INTERVAL_MS)

    def stop(self) -> None:
        self._stopping = True
        self._timer.stop()
        # Signal that this exit is intentional, so the helper won't relaunch.
        try:
            guardian_signal_path().write_text("shutdown", encoding="utf-8")
        except OSError as exc:
            log.warning("Could not write guardian signal: %s", exc)

        if self._helper is not None:
            self._terminate_helper()
        log.info("Guardian stopped.")

    def _spawn_helper(self) -> None:
        try:
            create_time = psutil.Process(os.getpid()).create_time()
        except psutil.Error:
            create_time = 0.0

        command = [
            sys.executable,
            "-m", "app_tracker.security.guardian_helper",
            str(os.getpid()),
            repr(create_time),
            str(guardian_signal_path()),
        ]
        kwargs = {
            "cwd": str(project_root()),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True

        try:
            self._helper = subprocess.Popen(command, **kwargs)
            log.info("Guardian helper started (PID %s).", self._helper.pid)
        except OSError as exc:
            log.error("Failed to start guardian helper: %s", exc)
            self._helper = None

    def _ensure_alive(self) -> None:
        if self._stopping:
            return
        if self._helper is None or self._helper.poll() is not None:
            log.warning("Guardian helper not running; restarting.")
            self._spawn_helper()

    def _terminate_helper(self) -> None:
        helper = self._helper
        self._helper = None
        if helper is None:
            return
        try:
            helper.terminate()
            try:
                helper.wait(timeout=2)
            except subprocess.TimeoutExpired:
                helper.kill()
        except OSError as exc:
            log.debug("Error terminating guardian helper: %s", exc)
