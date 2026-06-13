"""Runtime file-system locations.

Data (the SQLite database, logs and the guardian signal file) is stored in a
per-user application data directory instead of next to the source code. This
keeps the working tree clean and makes the app behave well when installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app_tracker.config import APP_NAME, DB_NAME, GUARDIAN_SHUTDOWN_SIGNAL_FILE

_DIR_SLUG = "AppTracker"


def data_dir() -> Path:
    """Return (creating if needed) the per-user data directory."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = Path(base) / _DIR_SLUG
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / _DIR_SLUG
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = Path(base) / _DIR_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / DB_NAME


def log_path() -> Path:
    return data_dir() / "app_tracker.log"


def guardian_signal_path() -> Path:
    return data_dir() / GUARDIAN_SHUTDOWN_SIGNAL_FILE


def project_root() -> Path:
    """Directory that contains the ``app_tracker`` package.

    Used as the working directory when the guardian relaunches the app via
    ``python -m app_tracker``.
    """
    return Path(__file__).resolve().parent.parent
