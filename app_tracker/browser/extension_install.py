"""Install the signed Firefox extension that ships with the repository.

The signed file lives in ``signed-extension/advanced-app-tracker.xpi``
(made with ``python tools/sign_extension.py``). Opening it with Firefox shows
the normal "Add extension?" prompt, and the extension stays installed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app_tracker.paths import project_root

log = logging.getLogger(__name__)

XPI_NAME = "advanced-app-tracker.xpi"


def signed_xpi_path() -> Path:
    return project_root() / "signed-extension" / XPI_NAME


def _windows_registry_firefox() -> Optional[str]:
    try:
        import winreg
    except ImportError:
        return None
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
                if value and Path(value).is_file():
                    return value
        except OSError:
            continue
    return None


def find_firefox() -> Optional[str]:
    """Return the path to firefox, or None if it is not installed."""
    found = shutil.which("firefox")
    if found:
        return found

    if sys.platform == "win32":
        from_registry = _windows_registry_firefox()
        if from_registry:
            return from_registry
        candidates = [
            Path(os.environ.get(var, "")) / "Mozilla Firefox" / "firefox.exe"
            for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
            if os.environ.get(var)
        ]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Firefox.app/Contents/MacOS/firefox")]
    else:
        candidates = []

    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def install_extension() -> tuple[bool, str]:
    """Open the signed extension in Firefox.

    Returns (success, message for the user).
    """
    xpi = signed_xpi_path()
    if not xpi.is_file():
        return False, (
            "Файл расширения не найден:\n"
            f"{xpi}\n\n"
            "Его создаёт автор репозитория командой "
            "python tools/sign_extension.py."
        )

    firefox = find_firefox()
    if firefox is None:
        return False, (
            "Firefox не найден. Установите Firefox или перетащите файл\n"
            f"{xpi}\nв окно Firefox вручную."
        )

    try:
        subprocess.Popen([firefox, str(xpi)])
    except OSError as exc:
        log.exception("Could not start Firefox")
        return False, f"Не удалось запустить Firefox:\n{exc}"

    return True, (
        "Firefox открыт. Нажмите «Добавить» в появившемся окне.\n"
        "После этого расширение останется установленным навсегда."
    )
