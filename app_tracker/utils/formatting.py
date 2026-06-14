"""Duration formatting/parsing and friendly application names."""

from __future__ import annotations

import os
from typing import Optional


def format_duration(seconds: Optional[int]) -> str:
    """Format a number of seconds as ``Xч Yм`` / ``Yм Zс`` / ``Zс``."""
    if seconds is None:
        return "N/A"
    seconds = max(0, int(seconds))

    if seconds < 60:
        return f"{seconds}с"
    if seconds < 3600:
        return f"{seconds // 60}м {seconds % 60}с"
    return f"{seconds // 3600}ч {(seconds % 3600) // 60}м"


_UNIT_SECONDS = {
    "ч": 3600, "h": 3600,
    "м": 60, "m": 60,
    "с": 1, "s": 1,
}


def parse_time_input(text: str) -> Optional[int]:
    """Parse a duration like ``"1ч 30м"`` or ``"45m"`` into seconds.

    Returns ``0`` for an empty string and ``None`` if anything can't be parsed.
    """
    if not text:
        return 0

    total = 0
    parsed_any = False
    for part in text.lower().split():
        unit = part[-1]
        if unit in _UNIT_SECONDS:
            number, multiplier = part[:-1], _UNIT_SECONDS[unit]
        else:
            number, multiplier = part, 1
        try:
            total += int(number) * multiplier
        except ValueError:
            return None
        parsed_any = True

    return total if parsed_any else None


def friendly_app_name(process_name: Optional[str], executable_path: Optional[str]) -> str:
    if not executable_path:
        return process_name or "Неизвестно"
    stem, _ = os.path.splitext(os.path.basename(executable_path))
    friendly = stem.replace("-", " ").replace("_", " ").title()
    return friendly or process_name or "Неизвестно"
