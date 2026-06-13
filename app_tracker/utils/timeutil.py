"""Date/time helpers."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple


def week_bounds(target: Optional[date] = None) -> Tuple[date, date]:
    """Return the Monday and Sunday bracketing ``target`` (today by default)."""
    target = target or date.today()
    start = target - timedelta(days=target.weekday())  # Monday == 0
    return start, start + timedelta(days=6)
