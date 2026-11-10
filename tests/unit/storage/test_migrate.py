"""Idempotent schema create."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dce.storage.migrate import migrate
from dce.storage.repository import SourceRecord, get_source, upsert_source

EXPECTED_TABLES = {
    "schema_migrations",
    "source_registry",
    "zcta_acs",
    "oews_wage",
    "ev_zip",
    "utility_rate",
    "rent_default",
    "extract_cache",
    "zip_county",
    "zip_cbsa",
    "zip_zcta",
    "delivery_center",
    "zcta_centroid",
    "zev_sales_zip",
    "zev_sales_county",
    "rent_cbsa",
    "rent_market",
    "rent_zip_obs",
    "rent_model_coeffs",
    "rent_resolved_cache",
    "rent_safmr",
    "zip_result",
}


def _connect(directory: Path) -> sqlite3.Connection:
    directory.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(directory / "dce.sqlite")


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def test_migrate_creates_dictionary_and_crosswalk_tables(tmp_path: Path) -> None:
    conn = _connect(tmp_path)
    try:
        migrate(conn)
        assert _table_names(conn) == EXPECTED_TABLES
        assert _column_names(conn, "source_registry") == [
            "source_id",
            "url",
            "as_of",
            "fetched_at",
            "ttl_days",
            "license_note",
            "bytes",
        ]
        assert "county_fips" in _column_names(conn, "zip_county")
        assert "cbsa" in _column_names(conn, "zip_cbsa")
        assert _column_names(conn, "zip_zcta") == ["zip", "zcta", "tot_ratio"]
        versions = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        assert versions == [(1,), (2,), (3,), (4,), (5,), (6,), (8,)]
        assert "median_home_value" in _column_names(conn, "zcta_acs")
        assert "households" in _column_names(conn, "zcta_acs")
        assert "median_gross_rent" in _column_names(conn, "zcta_acs")
        assert "land_sqmi" in _column_names(conn, "zcta_centroid")
    finally:
        conn.close()


def test_migrate_is_idempotent_and_keeps_rows(tmp_path: Path) -> None:
    conn = _connect(tmp_path)
    try:
        migrate(conn)
        migrate(conn)
        record = SourceRecord(
            source_id="hud_crosswalk",
            url="https://www.huduser.gov/portal/datasets/usps_crosswalk.html",
            as_of="2026-09-30",
            fetched_at="2026-11-09T05:00:00Z",
            ttl_days=180,
            license_note="HUD-USPS crosswalk. US government work.",
            byte_count=128,
        )
        upsert_source(conn, record)
        migrate(conn)
        assert get_source(conn, "hud_crosswalk") == record
        versions = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        assert versions == (7,)
    finally:
        conn.close()


def test_rent_market_table_heals_when_version_8_is_recorded_without_it(tmp_path: Path) -> None:
    conn = _connect(tmp_path)
    try:
        migrate(conn)
        assert "rent_market" in _tables(conn)
        conn.execute("DROP TABLE rent_market")
        conn.commit()
        migrate(conn)
        assert "url" in _column_names(conn, "rent_market")
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 8").fetchone()
        assert count == (1,)
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}
