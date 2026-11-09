"""Opening the user database creates it once."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dce.config import DB_FILENAME
from dce.storage.connection import get_connection
from dce.storage.repository import SourceRecord, get_source, upsert_source


def test_get_connection_creates_database_and_foreign_keys(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / "DeliveryCenterEstimator"
    conn = get_connection(directory)
    try:
        assert directory.is_dir()
        assert (directory / DB_FILENAME).is_file()
        flag = conn.execute("PRAGMA foreign_keys").fetchone()
        assert flag == (1,)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'source_registry'"
        ).fetchall()
        assert tables == [("source_registry",)]
    finally:
        conn.close()


def test_get_connection_is_idempotent(tmp_path: Path) -> None:
    record = SourceRecord(
        source_id="census_acs",
        url="https://www.census.gov/data/developers/data-sets/acs-5year.html",
        as_of="2024-12-31",
        fetched_at="2026-11-09T05:00:00Z",
        ttl_days=548,
        license_note="US Census Bureau. Public domain.",
        byte_count=64,
    )
    first = get_connection(tmp_path)
    try:
        upsert_source(first, record)
    finally:
        first.close()

    second = get_connection(tmp_path)
    try:
        assert get_source(second, "census_acs") == record
        versions = second.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert versions == [(1,), (2,), (3,), (4,)]
    finally:
        second.close()


def test_closed_database_stays_a_sqlite_file(tmp_path: Path) -> None:
    conn = get_connection(tmp_path)
    conn.close()
    probe = sqlite3.connect(tmp_path / DB_FILENAME)
    try:
        row = probe.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'zip_cbsa'"
        ).fetchone()
        assert row == ("zip_cbsa",)
    finally:
        probe.close()
