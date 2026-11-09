"""Typed read and write functions for SQLite.

Contract
--------
All SQL lives here (and in ``migrate``). Ingest modules return dataclasses;
the orchestrator passes those dataclasses to ``upsert_*``. ``load_*`` and
``get_*`` return dataclasses or ``None``. No business rules, no HTTP, no
cost math.

M1 implements the ``source_registry`` pair. The other DATA_DICTIONARY
tables and the ZIP crosswalk tables are created by ``migrate``. Later
milestones add one get/upsert pair per table instead of scattering SQL.

``upsert_source`` commits the connection so the row is durable.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRecord:
    """One ``source_registry`` row.

    ``as_of`` and ``fetched_at`` are ISO-8601 text. ``byte_count`` maps to
    the ``bytes`` column. Staleness is computed later from ``as_of`` and
    ``ttl_days``; it is not a column.
    """

    source_id: str
    url: str
    as_of: str | None
    fetched_at: str | None
    ttl_days: int
    license_note: str
    byte_count: int | None


def get_source(conn: sqlite3.Connection, source_id: str) -> SourceRecord | None:
    """Return one registry row, or ``None`` when it was never stored."""
    query = (
        "SELECT source_id, url, as_of, fetched_at, ttl_days, license_note, bytes "
        "FROM source_registry WHERE source_id = ?"
    )
    row = conn.execute(query, (source_id,)).fetchone()
    if row is None:
        return None
    return _source_from_row(row)


def upsert_source(conn: sqlite3.Connection, record: SourceRecord) -> None:
    """Insert or replace one registry row and commit."""
    conn.execute(
        """
        INSERT INTO source_registry (
            source_id, url, as_of, fetched_at, ttl_days, license_note, bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            url = excluded.url,
            as_of = excluded.as_of,
            fetched_at = excluded.fetched_at,
            ttl_days = excluded.ttl_days,
            license_note = excluded.license_note,
            bytes = excluded.bytes
        """,
        (
            record.source_id,
            record.url,
            record.as_of,
            record.fetched_at,
            record.ttl_days,
            record.license_note,
            record.byte_count,
        ),
    )
    conn.commit()


def _source_from_row(row: sqlite3.Row | tuple[object, ...]) -> SourceRecord:
    source_id, url, as_of, fetched_at, ttl_days, license_note, byte_count = row
    return SourceRecord(
        source_id=str(source_id),
        url=str(url),
        as_of=None if as_of is None else str(as_of),
        fetched_at=None if fetched_at is None else str(fetched_at),
        ttl_days=_required_int(ttl_days),
        license_note=str(license_note),
        byte_count=_optional_int(byte_count),
    )


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Expected an integer from SQLite, got {value!r}.")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value)
