"""Bundled resources (application icon)."""

from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent
APP_ICON_PATH = RESOURCES_DIR / "app_icon.png"


def app_icon_file() -> str:
    return str(APP_ICON_PATH)
