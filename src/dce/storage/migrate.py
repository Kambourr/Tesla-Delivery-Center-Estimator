"""Apply ``schema.sql`` idempotently.

Contract
--------
``migrate(conn) -> None`` runs the packaged schema against an open
connection. Repeating the call on a database that is already current
succeeds and leaves rows in place. No network.

Milestone M1 applies ``schema.sql`` (version 1). Later milestones that
change columns add a new ``schema_migrations`` version instead of editing
the version-1 statements in place.

Version 2 adds ``zcta_acs.median_home_value`` (ACS ``B25077_001E``). The
``ALTER`` lives here, not in ``schema.sql``, so repeating ``schema.sql``
stays valid.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _read_schema_sql() -> str:
    if not _SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Packaged schema is missing: {_SCHEMA_PATH}")
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the packaged schema. Safe to repeat."""
    conn.executescript(_read_schema_sql())
    _apply_version_2(conn)
    _apply_version_3(conn)


def _apply_version_2(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 2").fetchone()
    if existing is not None:
        return
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(zcta_acs)")}
    if "median_home_value" not in columns:
        conn.execute("ALTER TABLE zcta_acs ADD COLUMN median_home_value REAL")
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (2, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()


# Version 3 adds the catchment inputs. Version-1 statements in schema.sql
# stay as they were. CREATE IF NOT EXISTS keeps a second migrate safe.
_VERSION_3_SQL = """
CREATE TABLE IF NOT EXISTS delivery_center (
    center_id TEXT NOT NULL CHECK (length(center_id) > 0),
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL CHECK (length(state) = 2),
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    lat REAL NOT NULL CHECK (lat >= -90 AND lat <= 90),
    lon REAL NOT NULL CHECK (lon >= -180 AND lon <= 180),
    location_type TEXT NOT NULL CHECK (
        location_type IN ('delivery', 'store', 'service', 'hub', 'possible_handover')
    ),
    as_of TEXT NOT NULL,
    coordinate_basis TEXT NOT NULL,
    PRIMARY KEY (center_id, as_of)
);

CREATE TABLE IF NOT EXISTS zcta_centroid (
    zcta TEXT NOT NULL CHECK (length(zcta) = 5),
    lat REAL NOT NULL CHECK (lat >= -90 AND lat <= 90),
    lon REAL NOT NULL CHECK (lon >= -180 AND lon <= 180),
    vintage TEXT NOT NULL,
    as_of TEXT NOT NULL,
    PRIMARY KEY (zcta, vintage)
);

CREATE TABLE IF NOT EXISTS zev_sales_zip (
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    state TEXT NOT NULL CHECK (length(state) = 2),
    data_year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    fuel_type TEXT NOT NULL,
    vehicles INTEGER NOT NULL CHECK (vehicles >= 0),
    as_of TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('cec', 'fallback')),
    PRIMARY KEY (zip, data_year, quarter, fuel_type, source)
);

CREATE TABLE IF NOT EXISTS zev_sales_county (
    county TEXT NOT NULL,
    state TEXT NOT NULL CHECK (length(state) = 2),
    data_year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    fuel_type TEXT NOT NULL,
    make TEXT NOT NULL,
    vehicles INTEGER NOT NULL CHECK (vehicles >= 0),
    as_of TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('cec', 'fallback')),
    PRIMARY KEY (county, data_year, quarter, fuel_type, make, source)
);
"""


def _apply_version_3(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone()
    if existing is not None:
        return
    conn.executescript(_VERSION_3_SQL)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (3, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()
