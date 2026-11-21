"""Read-only summaries of browser activity for the UI.

Every function takes the shared DatabaseManager and an inclusive date range.
Only finished sessions (with a duration) are counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

from app_tracker.core.database import DatabaseManager

_FINISHED = "duration_seconds > 0 AND DATE(start_time) BETWEEN DATE(?) AND DATE(?)"


@dataclass(frozen=True)
class DomainStat:
    domain: str
    category: str
    seconds: int
    visits: int


def period_bounds(days: int, today: Optional[date] = None) -> Tuple[date, date]:
    """Return (start, end) for the last ``days`` days, today included."""
    today = today or date.today()
    days = max(1, int(days))
    return today - timedelta(days=days - 1), today


def total_seconds(db: DatabaseManager, start: date, end: date) -> int:
    row = db._fetch_one(
        f"SELECT COALESCE(SUM(duration_seconds), 0) FROM browser_activity WHERE {_FINISHED}",
        (start, end),
    )
    return int(row[0]) if row and row[0] else 0


def category_totals(db: DatabaseManager, start: date, end: date) -> List[Tuple[str, int]]:
    """Time per category, biggest first."""
    rows = db._fetch_all(
        f"""
        SELECT COALESCE(category, ''), SUM(duration_seconds) AS total
        FROM browser_activity WHERE {_FINISHED}
        GROUP BY category ORDER BY total DESC
        """,
        (start, end),
    )
    return [(cat or "Другое", int(total or 0)) for cat, total in rows]


def domain_totals(
    db: DatabaseManager, start: date, end: date, limit: int = 50
) -> List[DomainStat]:
    """Time per site, biggest first.

    A site can get different categories (a lecture vs. a music video on the
    same domain), so the category shown is the one with the most time.
    """
    rows = db._fetch_all(
        f"""
        SELECT domain, COALESCE(category, ''), SUM(duration_seconds), COUNT(*)
        FROM browser_activity WHERE {_FINISHED}
        GROUP BY domain, category
        """,
        (start, end),
    )
    merged: dict[str, dict] = {}
    for domain, category, seconds, visits in rows:
        seconds, visits = int(seconds or 0), int(visits or 0)
        item = merged.setdefault(
            domain, {"seconds": 0, "visits": 0, "category": category, "best": -1}
        )
        item["seconds"] += seconds
        item["visits"] += visits
        if seconds > item["best"]:
            item["best"] = seconds
            item["category"] = category

    stats = [
        DomainStat(domain, v["category"] or "Другое", v["seconds"], v["visits"])
        for domain, v in merged.items()
    ]
    stats.sort(key=lambda s: (-s.seconds, s.domain))
    return stats[:limit]
