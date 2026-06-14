"""Per-user filesystem locations for the database, logs and runtime files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app_tracker.config import DB_NAME, GUARDIAN_SHUTDOWN_SIGNAL_FILE

_DIR_SLUG = "AppTracker"


def data_dir() -> Path:
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
    return Path(__file__).resolve().parent.parent
