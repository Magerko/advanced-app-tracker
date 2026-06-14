"""Cross-platform detection of the current foreground window.

Each platform has a native implementation, with a pygetwindow (title-only)
fallback. Callers get ``None`` when nothing useful can be determined.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import NamedTuple, Optional

import psutil

log = logging.getLogger(__name__)


class ActiveWindowInfo(NamedTuple):
    pid: Optional[int]
    process_name: Optional[str]
    executable_path: Optional[str]
    window_title: Optional[str]


try:
    import pygetwindow as _gw
except Exception:
    _gw = None


# Windows
_win_user32 = None
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes

        _win_user32 = ctypes.windll.user32
        _win_user32.GetForegroundWindow.restype = wintypes.HWND
        _win_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        _win_user32.GetWindowTextLengthW.restype = ctypes.c_int
        _win_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _win_user32.GetWindowTextW.restype = ctypes.c_int
        _win_user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        _win_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    except (AttributeError, OSError) as exc:
        log.warning("Windows window APIs unavailable: %s", exc)
        _win_user32 = None


def _active_window_windows() -> Optional[ActiveWindowInfo]:
    if _win_user32 is None:
        return None
    try:
        hwnd = _win_user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid_holder = wintypes.DWORD()
        _win_user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_holder))
        pid = pid_holder.value
        if not pid:
            return None

        length = _win_user32.GetWindowTextLengthW(hwnd) + 1
        buffer = ctypes.create_unicode_buffer(length)
        _win_user32.GetWindowTextW(hwnd, buffer, length)

        proc = psutil.Process(pid)
        with proc.oneshot():
            return ActiveWindowInfo(pid, proc.name(), proc.exe(), buffer.value)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        log.debug("Windows active window lookup failed: %s", exc)
        return None


# macOS
_macos_ok = False
if sys.platform == "darwin":
    try:
        from AppKit import NSWorkspace  # noqa: F401
        import Quartz  # noqa: F401

        _macos_ok = True
    except ImportError:
        log.warning("macOS window APIs unavailable (pyobjc not installed).")


def _active_window_macos() -> Optional[ActiveWindowInfo]:
    if not _macos_ok:
        return None
    try:
        from AppKit import NSWorkspace
        import Quartz

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not app:
            return None
        pid = app.processIdentifier()
        proc = psutil.Process(pid)
        with proc.oneshot():
            name, exe = proc.name(), proc.exe()
        title = app.localizedName()
        try:
            options = (
                Quartz.kCGWindowListOptionOnScreenOnly
                | Quartz.kCGWindowListExcludeDesktopElements
            )
            for window in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []:
                if window.get(Quartz.kCGWindowOwnerPID) == pid:
                    candidate = window.get(Quartz.kCGWindowName)
                    if candidate:
                        title = candidate
                        break
        except Exception:
            pass
        return ActiveWindowInfo(pid, name, exe, title)
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as exc:
        log.debug("macOS active window lookup failed: %s", exc)
        return None


# Linux (X11)
_x11 = None
if sys.platform.startswith("linux") and "WAYLAND_DISPLAY" not in os.environ:
    try:
        from Xlib import display

        _x11_display = display.Display()
        _x11 = {
            "display": _x11_display,
            "root": _x11_display.screen().root,
            "active": _x11_display.intern_atom("_NET_ACTIVE_WINDOW"),
            "pid": _x11_display.intern_atom("_NET_WM_PID"),
            "name": _x11_display.intern_atom("_NET_WM_NAME"),
            "utf8": _x11_display.intern_atom("UTF8_STRING"),
        }
    except Exception as exc:
        log.warning("X11 window APIs unavailable: %s", exc)
        _x11 = None


def _active_window_linux() -> Optional[ActiveWindowInfo]:
    if _x11 is None:
        return None
    try:
        from Xlib import X

        root, disp = _x11["root"], _x11["display"]
        prop = root.get_property(_x11["active"], X.AnyPropertyType, 0, 1)
        if not prop or not prop.value:
            return None
        window = disp.create_resource_object("window", prop.value[0])

        pid_prop = window.get_property(_x11["pid"], X.AnyPropertyType, 0, 1)
        if not pid_prop or not pid_prop.value:
            return None
        pid = pid_prop.value[0]

        title = None
        name_prop = window.get_property(_x11["name"], _x11["utf8"], 0, 1024)
        if name_prop and name_prop.value:
            title = name_prop.value.decode("utf-8", "ignore")

        proc = psutil.Process(pid)
        with proc.oneshot():
            name, exe = proc.name(), proc.exe()
        disp.sync()
        return ActiveWindowInfo(pid, name, exe, title)
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as exc:
        log.debug("X11 active window lookup failed: %s", exc)
        return None


def _active_window_fallback() -> Optional[ActiveWindowInfo]:
    if _gw is None:
        return None
    try:
        window = _gw.getActiveWindow()
        if window and getattr(window, "title", None):
            return ActiveWindowInfo(None, None, None, window.title)
    except Exception:
        pass
    return None


def get_active_window_info() -> Optional[ActiveWindowInfo]:
    """Return information about the foreground window, or ``None``."""
    if sys.platform == "win32":
        info = _active_window_windows()
    elif sys.platform == "darwin":
        info = _active_window_macos()
    elif sys.platform.startswith("linux"):
        info = _active_window_linux()
    else:
        info = None

    if info is None:
        info = _active_window_fallback()

    if info and info.executable_path:
        try:
            info = info._replace(executable_path=os.path.normpath(info.executable_path))
        except Exception:
            pass
    return info
