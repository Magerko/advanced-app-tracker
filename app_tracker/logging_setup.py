"""Central logging configuration.

Every module obtains its logger via ``logging.getLogger(__name__)`` and stays
silent until :func:`configure_logging` wires up the handlers. Logs go both to
the console and to a rotating file in the data directory.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app_tracker.paths import log_path

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_configured = False


def configure_logging(level: int = logging.INFO, tag: str = "") -> None:
    """Initialise root logging once. ``tag`` is prefixed to the logger name
    (useful to distinguish the main process from the guardian helper)."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        file_handler = RotatingFileHandler(
            log_path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - disk/permission edge case
        root.warning("Could not open log file: %s", exc)

    if tag:
        logging.getLogger(tag).info("Logging initialised (%s)", tag)
    _configured = True
