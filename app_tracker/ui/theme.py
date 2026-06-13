"""Application theming (a Fusion-based dark palette) and the window icon."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPalette

from app_tracker.resources import APP_ICON_PATH

log = logging.getLogger(__name__)

_WINDOW = QColor(53, 53, 53)
_BASE = QColor(60, 63, 65)
_HIGHLIGHT = QColor(42, 130, 218)
_DISABLED = QColor(160, 160, 160)
_WHITE = Qt.GlobalColor.white


def build_dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, _WINDOW)
    p.setColor(QPalette.ColorRole.WindowText, _WHITE)
    p.setColor(QPalette.ColorRole.Base, _BASE)
    p.setColor(QPalette.ColorRole.AlternateBase, _WINDOW)
    p.setColor(QPalette.ColorRole.Text, _WHITE)
    p.setColor(QPalette.ColorRole.Button, _WINDOW)
    p.setColor(QPalette.ColorRole.ButtonText, _WHITE)
    p.setColor(QPalette.ColorRole.Highlight, _HIGHLIGHT)
    p.setColor(QPalette.ColorRole.HighlightedText, _WHITE)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, _HIGHLIGHT)
    p.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
    p.setColor(QPalette.ColorRole.ToolTipText, _WHITE)

    disabled = QPalette.ColorGroup.Disabled
    p.setColor(disabled, QPalette.ColorRole.WindowText, _DISABLED)
    p.setColor(disabled, QPalette.ColorRole.Text, _DISABLED)
    p.setColor(disabled, QPalette.ColorRole.ButtonText, _DISABLED)
    p.setColor(disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    p.setColor(disabled, QPalette.ColorRole.HighlightedText, _DISABLED)
    return p


def app_icon() -> QIcon:
    """Return the bundled icon, falling back to a themed system icon."""
    if APP_ICON_PATH.exists():
        return QIcon(str(APP_ICON_PATH))
    return QIcon.fromTheme("utilities-system-monitor")
