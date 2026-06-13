"""Productivity classification of applications.

The integer values are persisted in the database, so they must stay stable.
``IntEnum`` lets the values be used interchangeably with the raw ints that
come back from SQLite.
"""

from __future__ import annotations

from enum import IntEnum


class Productivity(IntEnum):
    UNKNOWN = 0
    PRODUCTIVE = 1
    UNPRODUCTIVE = 2

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def rgb(self) -> tuple[int, int, int]:
        return _COLORS[self]

    @classmethod
    def from_value(cls, value: int) -> "Productivity":
        try:
            return cls(int(value))
        except (ValueError, TypeError):
            return cls.UNKNOWN


_LABELS = {
    Productivity.UNKNOWN: "Неизвестно",
    Productivity.PRODUCTIVE: "Продуктивно",
    Productivity.UNPRODUCTIVE: "Непродуктивно",
}

# Background colours used in tables (RGB). Tuned for the dark theme.
_COLORS = {
    Productivity.PRODUCTIVE: (180, 255, 180),    # light green
    Productivity.UNPRODUCTIVE: (255, 180, 180),  # light red
    Productivity.UNKNOWN: (100, 100, 100),       # dark grey
}

# Convenience aliases kept for readability at call sites.
PRODUCTIVITY_MAP = _LABELS
PRODUCTIVITY_COLORS = _COLORS
