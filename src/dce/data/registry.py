"""Source registry staleness flags.

Contract
--------
``staleness_status(as_of, ttl_days, today) -> "fresh" | "aging" | "stale" | "missing"``

Compare a source ``as_of`` date with its TTL. ``missing`` means no ``as_of``.
The status is not a database column. ``source_registry`` stores ``as_of``,
``fetched_at``, and ``ttl_days``; this function classifies them.

``ttl_days`` is the stale horizon from ``docs/DATA_SOURCES.md``. Aging is the
second half of that horizon, which matches the broker-rent rule (aging after
2 quarters, stale after 4) when the caller passes 4 quarters as ``ttl_days``.
ACS, OEWS, and California vehicle counts use :data:`TTL_18_MONTHS_DAYS`.

The function is pure: it does not read the clock, the database, or the network.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

Staleness = Literal["fresh", "aging", "stale", "missing"]

# 18 months counted as 365 + 183 days. DATA_SOURCES marks ACS, OEWS, and the
# California vehicle file stale when as_of is older than 18 months.
TTL_18_MONTHS_DAYS = 548


def staleness_status(as_of: date | None, ttl_days: int, today: date) -> Staleness:
    """Classify one source as fresh, aging, stale, or missing.

    * ``as_of is None`` → ``missing``
    * age ≤ half of ``ttl_days`` → ``fresh`` (an ``as_of`` in the future is fresh)
    * half of ``ttl_days`` < age ≤ ``ttl_days`` → ``aging``
    * age > ``ttl_days`` → ``stale``

    Half-days use integer arithmetic: age is fresh while ``age * 2 <= ttl_days``.
    ``ttl_days`` of 0 is fresh only on the ``as_of`` day. A negative TTL raises
    ``ValueError``.
    """
    if as_of is None:
        return "missing"
    ttl = _require_ttl(ttl_days)
    age_days = (_calendar_date(today) - _calendar_date(as_of)).days
    if age_days < 0 or age_days * 2 <= ttl:
        return "fresh"
    if age_days <= ttl:
        return "aging"
    return "stale"


def parse_as_of(value: str | None) -> date | None:
    """Parse a registry ``as_of`` value. Blank is missing. Anything else must be ISO."""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"as_of must be an ISO date, got {value!r}.") from exc


def _require_ttl(ttl_days: int) -> int:
    if isinstance(ttl_days, bool) or not isinstance(ttl_days, int):
        raise ValueError(f"ttl_days must be an integer >= 0, got {ttl_days!r}.")
    if ttl_days < 0:
        raise ValueError(f"ttl_days must be >= 0, got {ttl_days}.")
    return ttl_days


def _calendar_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if type(value) is not date:
        raise ValueError(f"Expected a date, got {value!r}.")
    return value
