"""Source registry and staleness flags.

Contract
--------
``staleness_status(as_of, ttl_days, today) -> "fresh" | "aging" | "stale" | "missing"``

Compare a source ``as_of`` date with its TTL. ``missing`` means no ``as_of``.
Cadence is per source (see ``docs/DATA_SOURCES.md``): for example ACS and
OEWS go stale after 18 months, broker rent ages after 2 quarters and is
stale after 4, GSA ages after 90 days. This function is pure: no clock
read inside the function beyond the ``today`` argument, no I/O, no network.

Later milestones also upsert ``source_registry`` rows
(``source_id``, ``url``, ``as_of``, ``fetched_at``, ``ttl_days``,
``license_note``, ``bytes``).

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

Staleness = Literal["fresh", "aging", "stale", "missing"]


def staleness_status(as_of: date | None, ttl_days: int, today: date) -> Staleness:
    """Classify one source as fresh, aging, stale, or missing. Not implemented in M0."""
    raise NotImplementedError("dce.data.registry.staleness_status is a stub (M0)")
