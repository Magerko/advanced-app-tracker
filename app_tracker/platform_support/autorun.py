"""Start-with-Windows support via the ``HKCU\\...\\Run`` registry key.

No-ops gracefully on non-Windows platforms (returns ``False``).
"""

from __future__ import annotations

import logging
import sys

from app_tracker.platform_support.launch import launch_command_string

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autorun(value_name: str, enable: bool = True) -> bool:
    """Enable or disable autostart. Returns ``True`` on success."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_WRITE) as key:
            if enable:
                winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, launch_command_string())
                log.info("Autorun enabled for %s.", value_name)
            else:
                try:
                    winreg.DeleteValue(key, value_name)
                    log.info("Autorun disabled for %s.", value_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        log.error("Could not update autorun: %s", exc)
        return False


def is_autorun_enabled(value_name: str) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, value_name)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
