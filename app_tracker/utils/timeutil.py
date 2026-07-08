from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple


def week_bounds(target: Optional[date] = None) -> Tuple[date, date]:
    target = target or date.today()
    start = target - timedelta(days=target.weekday())
    return start, start + timedelta(days=6)
