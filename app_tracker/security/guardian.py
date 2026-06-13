"""The guardian: an opt-in anti-kill watchdog.

A small helper process watches the main application's PID. If the application
disappears *without* having requested a clean shutdown, the helper relaunches
it. This is the core "self-control" feature: closing the app normally requires
the exit password, and killing it from Task Manager simply brings it back.

Safety is built in:

* A **clean shutdown is always honoured** - on a legitimate exit the main app
  writes a signal file and the helper exits without relaunching.
* PID reuse is guarded by comparing the process **create time**.
* A relaunch **back-off** (``GUARDIAN_MAX_RELAUNCHES`` within
  ``GUARDIAN_RELAUNCH_WINDOW_SECONDS``) prevents crash-loops from spinning up
  endless processes.

This class is the in-app *manager*; the watching loop lives in
:mod:`app_tracker.security.guardian_helper`.
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

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        """Clear any stale shutdown signal and spawn the helper."""
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
        """Request a clean shutdown: signal the helper and terminate it."""
        self._stopping = True
        self._timer.stop()
        # Tell the helper "this exit is intentional, do not relaunch".
        try:
            guardian_signal_path().write_text("shutdown", encoding="utf-8")
        except OSError as exc:
            log.warning("Could not write guardian signal: %s", exc)

        if self._helper is not None:
            self._terminate_helper()
        log.info("Guardian stopped.")

    # -- internals ------------------------------------------------------------
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
        """Restart the helper if it exited while we are still running."""
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
