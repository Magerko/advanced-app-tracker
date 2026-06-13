"""Application bootstrap: build the QApplication and run the main window."""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from app_tracker.config import APP_NAME, ORG_NAME, SETTING_START_MINIMIZED
from app_tracker.core.database import DatabaseManager
from app_tracker.logging_setup import configure_logging
from app_tracker.ui.main_window import MainWindow
from app_tracker.ui.theme import app_icon, build_dark_palette

log = logging.getLogger(__name__)


def run() -> int:
    configure_logging(tag="app")
    log.info("Starting %s", APP_NAME)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setPalette(build_dark_palette())
    # Hiding the window to the tray must not quit the app; explicit quit only.
    app.setQuitOnLastWindowClosed(False)

    try:
        db = DatabaseManager()
    except Exception as exc:  # pragma: no cover - DB init is critical
        log.exception("Database initialisation failed")
        QMessageBox.critical(None, APP_NAME, f"Не удалось открыть базу данных:\n{exc}")
        return 1

    try:
        window = MainWindow(db)
    except Exception as exc:  # pragma: no cover
        log.exception("Failed to create main window")
        QMessageBox.critical(None, APP_NAME, f"Ошибка запуска интерфейса:\n{exc}")
        db.close()
        return 1

    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    if db.get_bool(SETTING_START_MINIMIZED) and tray_available:
        log.info("Starting minimized to tray.")
    else:
        window.show()

    return app.exec()


def main() -> None:
    sys.exit(run())
