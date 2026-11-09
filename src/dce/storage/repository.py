"""Typed read and write functions for SQLite.

Contract
--------
All SQL lives here (and in ``migrate``). Ingest modules return dataclasses;
the orchestrator passes those dataclasses to ``upsert_*``. ``load_*`` and
``get_*`` return dataclasses or ``None``. No business rules, no HTTP, no
cost math.

M1 adds the ``source_registry`` pair below and the other DATA_DICTIONARY
tables. Later milestones add one get/upsert pair per new table instead of
scattering SQL.

Milestone M0: both functions raise ``NotImplementedError``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRecord:
    """One ``source_registry`` row. Dates are ISO-8601 text."""

    source_id: str
    url: str
    as_of: str | None
    fetched_at: str | None
    ttl_days: int
    license_note: str
    byte_count: int | None


def get_source(conn: sqlite3.Connection, source_id: str) -> SourceRecord | None:
    """Return one registry row, or ``None`` when it was never stored."""
    raise NotImplementedError("dce.storage.repository.get_source is a stub (M0)")


def upsert_source(conn: sqlite3.Connection, record: SourceRecord) -> None:
    """Insert or replace one registry row."""
    raise NotImplementedError("dce.storage.repository.upsert_source is a stub (M0)")
