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

Version 4 adds ``zcta_acs.households`` (ACS ``B11001_001E``). The
non-California demand fallback weights ZIPs by that count. Version 3
(catchment tables) is unchanged.

Version 5 adds the nationwide ZIP inputs: ACS median gross rent, gazetteer
land area, crosswalk names and ratios, and the rent-resolution tables from
``docs/DATA_SOURCES.md`` section 8 plus ``rent_safmr``.

Version 6 adds ``zip_result``, the precomputed estimate for one ZIP. The
row is replaced when the model version or the inputs hash changes.

Version 7 stores ``payload_json`` as a BLOB. New rows are zlib-compressed
JSON. A version-6 text value copied into the new table is left as text, and
the reader accepts both.

Version 8 adds ``rent_market``: broker market-report asking rents by county
or CBSA, loaded from ``data/seed/rent_market.csv``.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _schema_path() -> Path:
    """Return ``schema.sql``, including the copy PyInstaller places in ``_MEIPASS``."""
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str) and meipass:
        bundled = Path(meipass) / "dce" / "storage" / "schema.sql"
        if bundled.is_file():
            return bundled
    return Path(__file__).with_name("schema.sql")


def _read_schema_sql() -> str:
    path = _schema_path()
    if not path.is_file():
        raise FileNotFoundError(f"Packaged schema is missing: {path}")
    return path.read_text(encoding="utf-8")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the packaged schema. Safe to repeat."""
    conn.executescript(_read_schema_sql())
    _apply_version_2(conn)
    _apply_version_3(conn)
    _apply_version_4(conn)
    _apply_version_5(conn)
    _apply_version_6(conn)
    _apply_version_7(conn)
    _apply_version_8(conn)


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


def _apply_version_4(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 4").fetchone()
    if existing is not None:
        return
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(zcta_acs)")}
    if "households" not in columns:
        conn.execute("ALTER TABLE zcta_acs ADD COLUMN households REAL")
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (4, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


_VERSION_5_SQL = """
CREATE TABLE IF NOT EXISTS rent_cbsa (
    cbsa TEXT NOT NULL CHECK (length(cbsa) = 5),
    property_type TEXT NOT NULL,
    rent_psf_year REAL NOT NULL CHECK (rent_psf_year >= 0),
    as_of TEXT NOT NULL,
    citation TEXT NOT NULL,
    broker TEXT NOT NULL,
    fetched_at TEXT,
    PRIMARY KEY (cbsa, property_type, as_of)
);

CREATE TABLE IF NOT EXISTS rent_zip_obs (
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    property_type TEXT NOT NULL,
    rent_psf_year REAL NOT NULL CHECK (rent_psf_year >= 0),
    as_of TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('gsa', 'assessor', 'model')),
    n_leases INTEGER,
    citation TEXT NOT NULL,
    PRIMARY KEY (zip, property_type, source, as_of)
);

CREATE TABLE IF NOT EXISTS rent_model_coeffs (
    model_id TEXT PRIMARY KEY,
    formula_json TEXT NOT NULL,
    trained_on TEXT NOT NULL,
    as_of TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rent_resolved_cache (
    zip TEXT PRIMARY KEY CHECK (length(zip) = 5),
    rent_psf_year REAL NOT NULL,
    property_type TEXT NOT NULL,
    tier TEXT NOT NULL,
    confidence TEXT NOT NULL,
    as_of TEXT NOT NULL,
    components_json TEXT NOT NULL,
    resolved_at TEXT NOT NULL,
    citation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rent_safmr (
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    rent_2br_month REAL NOT NULL CHECK (rent_2br_month >= 0),
    as_of TEXT NOT NULL,
    citation TEXT NOT NULL,
    PRIMARY KEY (zip, as_of)
);
"""


def _apply_version_5(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 5").fetchone()
    if existing is not None:
        return
    _ensure_column(conn, "zcta_acs", "median_gross_rent", "REAL")
    _ensure_column(conn, "zcta_centroid", "land_sqmi", "REAL")
    _ensure_column(conn, "zip_zcta", "tot_ratio", "REAL")
    _ensure_column(conn, "zip_county", "county_name", "TEXT")
    _ensure_column(conn, "zip_cbsa", "cbsa_name", "TEXT")
    conn.executescript(_VERSION_5_SQL)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (5, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()


_VERSION_6_SQL = """
CREATE TABLE IF NOT EXISTS zip_result (
    zip TEXT PRIMARY KEY CHECK (length(zip) = 5),
    model_version TEXT NOT NULL,
    inputs_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    reason TEXT,
    payload_json TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    elapsed_ms REAL
);

CREATE INDEX IF NOT EXISTS zip_result_fresh
    ON zip_result (model_version, inputs_hash, status);
"""


def _apply_version_6(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 6").fetchone()
    if existing is not None:
        return
    conn.executescript(_VERSION_6_SQL)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (6, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()


_VERSION_7_TABLE = """
CREATE TABLE zip_result_v7 (
    zip TEXT PRIMARY KEY CHECK (length(zip) = 5),
    model_version TEXT NOT NULL,
    inputs_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    reason TEXT,
    payload_json BLOB NOT NULL,
    computed_at TEXT NOT NULL,
    elapsed_ms REAL
)
"""


def _apply_version_7(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 7").fetchone()
    if existing is not None:
        return
    payload_type = ""
    for row in conn.execute("PRAGMA table_info(zip_result)"):
        if str(row[1]) == "payload_json":
            payload_type = str(row[2])
    if payload_type.upper() != "BLOB":
        conn.execute("DROP INDEX IF EXISTS zip_result_fresh")
        conn.execute(_VERSION_7_TABLE)
        conn.execute(
            "INSERT INTO zip_result_v7 ("
            "zip, model_version, inputs_hash, status, reason, payload_json, computed_at, elapsed_ms"
            ") SELECT zip, model_version, inputs_hash, status, reason, payload_json, "
            "computed_at, elapsed_ms FROM zip_result"
        )
        conn.execute("DROP TABLE zip_result")
        conn.execute("ALTER TABLE zip_result_v7 RENAME TO zip_result")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS zip_result_fresh "
            "ON zip_result (model_version, inputs_hash, status)"
        )
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (7, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()


_VERSION_8_SQL = """
CREATE TABLE IF NOT EXISTS rent_market (
    geography_level TEXT NOT NULL CHECK (geography_level IN ('county', 'cbsa')),
    geography_id TEXT NOT NULL CHECK (length(geography_id) = 5),
    market TEXT NOT NULL,
    submarket TEXT NOT NULL,
    property_type TEXT NOT NULL,
    rent_psf_year REAL NOT NULL CHECK (rent_psf_year > 0),
    reported_rent REAL NOT NULL CHECK (reported_rent > 0),
    reported_unit TEXT NOT NULL,
    reported_basis TEXT NOT NULL,
    source TEXT NOT NULL,
    report TEXT NOT NULL,
    quarter TEXT NOT NULL,
    as_of TEXT NOT NULL,
    url TEXT NOT NULL,
    note TEXT NOT NULL,
    fetched_at TEXT,
    PRIMARY KEY (geography_level, geography_id)
);
"""


def _apply_version_8(conn: sqlite3.Connection) -> None:
    # CREATE ... IF NOT EXISTS runs every time, so a database whose version 8
    # row was written without this table (for example by another branch
    # sharing the same user directory) still gets it.
    conn.executescript(_VERSION_8_SQL)
    existing = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 8").fetchone()
    if existing is not None:
        return
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) "
        "VALUES (8, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    )
    conn.commit()
