"""Static configuration: identifiers, formats, defaults and setting keys.

Only constants live here. Anything that has to be computed at runtime
(data directories, file paths) belongs in :mod:`app_tracker.paths`.
"""

from app_tracker import __app_name__, __version__

# --- Application identity ----------------------------------------------------
APP_NAME = __app_name__
APP_VERSION = __version__
ORG_NAME = "AppTracker"
# Registry value / settings key used for Windows autorun.
AUTORUN_REGISTRY_NAME = APP_NAME

# --- Persistence -------------------------------------------------------------
DB_NAME = "app_tracker.db"

# --- Formats -----------------------------------------------------------------
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"

# --- Tracking behaviour ------------------------------------------------------
UPDATE_INTERVAL_MS = 1000
DEFAULT_IDLE_THRESHOLD_SECONDS = 60
HISTORY_DEFAULT_DAYS = 7
GRAPH_PIE_MAX_SLICES = 10

# Foreground processes that are never worth tracking as "apps".
IGNORED_EXECUTABLES = {
    "explorer.exe",
    "searchapp.exe",
    "searchhost.exe",
    "snippingtool.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "lockapp.exe",
    "textinputhost.exe",
}

# --- Guardian / watchdog -----------------------------------------------------
WATCHDOG_CHECK_INTERVAL_MS = 15_000           # main process polls its helper
GUARDIAN_POLL_INTERVAL_SECONDS = 5            # helper polls the main process
GUARDIAN_SHUTDOWN_SIGNAL_FILE = "guardian_shutdown.signal"
# Relaunch back-off: never relaunch more than this many times within the window.
GUARDIAN_MAX_RELAUNCHES = 5
GUARDIAN_RELAUNCH_WINDOW_SECONDS = 120

# --- Setting keys (stored in the ``settings`` table) -------------------------
SETTING_IDLE_THRESHOLD = "idle_threshold_seconds"
SETTING_TERMINATE_ON_LIMIT = "terminate_on_limit"
SETTING_AUTORUN_ENABLED = "autorun_enabled_win"
SETTING_START_MINIMIZED = "start_minimized"
SETTING_MINIMIZE_TO_TRAY = "minimize_to_tray"
SETTING_GUARDIAN_ENABLED = "guardian_enabled"
SETTING_PASSWORD_PROTECT_EXIT = "password_protect_exit"
SETTING_PASSWORD_HASH = "exit_password_hash"
SETTING_CLOSE_HINT_SHOWN = "close_to_tray_hint_shown"

# Keys whose values are UTF-8 text (everything except the raw password hash).
TEXT_SETTING_KEYS = frozenset({
    SETTING_IDLE_THRESHOLD,
    SETTING_TERMINATE_ON_LIMIT,
    SETTING_AUTORUN_ENABLED,
    SETTING_START_MINIMIZED,
    SETTING_MINIMIZE_TO_TRAY,
    SETTING_GUARDIAN_ENABLED,
    SETTING_PASSWORD_PROTECT_EXIT,
    SETTING_CLOSE_HINT_SHOWN,
})
