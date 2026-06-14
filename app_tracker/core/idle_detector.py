"""User-idle detection from global mouse/keyboard activity via pynput.

If pynput is unavailable the detector degrades gracefully and never reports
the user as idle.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger(__name__)

try:
    from pynput import keyboard, mouse
    _PYNPUT_AVAILABLE = True
except Exception as exc:  # ImportError, or a platform/permission failure
    keyboard = mouse = None  # type: ignore
    _PYNPUT_AVAILABLE = False
    log.warning("pynput unavailable (%s). Idle detection disabled.", exc)


class IdleDetector(QObject):
    """Emits idle_changed (True = idle) when the idle state flips."""

    idle_changed = pyqtSignal(bool)

    _ACTIVITY_DEBOUNCE_S = 0.5

    def __init__(self, threshold_seconds: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._threshold = max(1, int(threshold_seconds))
        self._last_activity = time.monotonic()
        self._is_idle = False
        self._lock = Lock()
        self._running = False
        self._mouse_listener = None
        self._keyboard_listener = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_idle)

    @property
    def available(self) -> bool:
        return _PYNPUT_AVAILABLE

    @property
    def is_idle(self) -> bool:
        with self._lock:
            return self._is_idle

    # Listener callbacks run on pynput's own threads.
    def _on_activity(self, *_args) -> None:
        emit_active = False
        with self._lock:
            now = time.monotonic()
            if self._is_idle or (now - self._last_activity) > self._ACTIVITY_DEBOUNCE_S:
                self._last_activity = now
                if self._is_idle:
                    self._is_idle = False
                    emit_active = True
        if emit_active:
            self.idle_changed.emit(False)

    def _check_idle(self) -> None:
        emit_idle = False
        with self._lock:
            if (
                self._running
                and not self._is_idle
                and (time.monotonic() - self._last_activity) >= self._threshold
            ):
                self._is_idle = True
                emit_idle = True
        if emit_idle:
            self.idle_changed.emit(True)

    def start(self) -> None:
        if self._running or not _PYNPUT_AVAILABLE:
            return
        try:
            self._mouse_listener = mouse.Listener(
                on_move=self._on_activity,
                on_click=self._on_activity,
                on_scroll=self._on_activity,
            )
            self._keyboard_listener = keyboard.Listener(on_press=self._on_activity)
            self._mouse_listener.start()
            self._keyboard_listener.start()
        except Exception as exc:
            log.error("Could not start pynput listeners: %s. Idle detection off.", exc)
            self._stop_listeners()
            return

        with self._lock:
            self._running = True
            self._last_activity = time.monotonic()
            self._is_idle = False
        self._timer.start(1000)
        log.info("Idle detector started (threshold %ss).", self._threshold)

    def stop(self) -> None:
        if not self._running:
            return
        with self._lock:
            self._running = False
        self._timer.stop()
        self._stop_listeners()
        log.info("Idle detector stopped.")

    def _stop_listeners(self) -> None:
        for listener in (self._mouse_listener, self._keyboard_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception as exc:
                    log.debug("Error stopping listener: %s", exc)
        self._mouse_listener = self._keyboard_listener = None

    def set_threshold(self, seconds: int) -> None:
        with self._lock:
            self._threshold = max(1, int(seconds))
        log.info("Idle threshold updated to %ss.", self._threshold)
        if self._running:
            self._check_idle()
