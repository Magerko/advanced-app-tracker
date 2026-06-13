"""OS-specific helpers (active-window detection, Windows autorun)."""

from app_tracker.platform_support.active_window import (
    ActiveWindowInfo,
    get_active_window_info,
)
from app_tracker.platform_support.autorun import (
    is_autorun_enabled,
    set_autorun,
)

__all__ = [
    "ActiveWindowInfo",
    "get_active_window_info",
    "is_autorun_enabled",
    "set_autorun",
]
