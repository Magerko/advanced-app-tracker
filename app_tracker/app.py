"""Application bootstrap: build the QApplication and run the main window."""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QTabWidget

from app_tracker.browser.api import BrowserApiServer
from app_tracker.ui.browser_report_widget import BrowserReportWidget
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
    try:
        tab_bar = window.findChild(QTabWidget)
        if tab_bar is not None:
            tab_bar.addTab(BrowserReportWidget(db), "Браузер")
    except Exception:
        log.exception("Could not add the browser tab")

    # Optional browser-tab tracking: a local API that the browser extension
    # talks to. A busy port or a missing library must never stop the app.
    try:
        browser_storage = BrowserStorage(db)
        if browser_storage.is_enabled():
            browser_api = BrowserApiServer(
                browser_storage,
                db.get_int(SETTING_BROWSER_PORT, DEFAULT_BROWSER_API_PORT),
            )
            browser_api.start()
            app.aboutToQuit.connect(browser_api.stop)
    except Exception:
        log.exception("Browser tracking could not start")

    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    if db.get_bool(SETTING_START_MINIMIZED) and tray_available:
        log.info("Starting minimized to tray.")
    else:
        window.show()

    return app.exec()


def main() -> None:
    sys.exit(run())
