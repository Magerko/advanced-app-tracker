"""Application bootstrap: build the QApplication and run the main window."""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from app_tracker.browser.storage import BrowserStorage
from app_tracker.config import (
    APP_NAME,
    DEFAULT_BROWSER_API_PORT,
    ORG_NAME,
    SETTING_BROWSER_PORT,
    SETTING_START_MINIMIZED,
)
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
    # Closing to the tray must not quit; we quit explicitly instead.
    app.setQuitOnLastWindowClosed(False)

    try:
        db = DatabaseManager()
    except Exception as exc:
        log.exception("Database initialisation failed")
        QMessageBox.critical(None, APP_NAME, f"Не удалось открыть базу данных:\n{exc}")
        return 1

    try:
        window = MainWindow(db)
    except Exception as exc:
        log.exception("Failed to create main window")
        QMessageBox.critical(None, APP_NAME, f"Ошибка запуска интерфейса:\n{exc}")
        db.close()
        return 1
    _start_browser_api(app, db)

    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    if db.get_bool(SETTING_START_MINIMIZED) and tray_available:
        log.info("Starting minimized to tray.")
    else:
        window.show()

    return app.exec()


def _start_browser_api(app: QApplication, db: DatabaseManager) -> None:
    """Start the local API that the browser extension talks to.

    The server always runs (if fastapi is installed): the "record sites"
    switch is checked on every event, so it can be toggled without a restart.
    A busy port or a missing library must never stop the app.
    """
    try:
        from app_tracker.browser.api import BrowserApiServer
    except ImportError:
        log.warning(
            "Browser tracking is off: install fastapi and uvicorn "
            "(pip install -r requirements.txt)."
        )
        return
    try:
        server = BrowserApiServer(
            BrowserStorage(db),
            db.get_int(SETTING_BROWSER_PORT, DEFAULT_BROWSER_API_PORT),
        )
        server.start()
        app.aboutToQuit.connect(server.stop)
    except Exception:
        log.exception("Browser tracking could not start")


def main() -> None:
    sys.exit(run())
