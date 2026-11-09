"""source_registry insert and read."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dce.storage.connection import get_connection
from dce.storage.repository import SourceRecord, get_source, upsert_source

_ORIGINAL = SourceRecord(
    source_id="hud_crosswalk",
    url="https://www.huduser.gov/portal/datasets/usps_crosswalk.html",
    as_of="2026-09-30",
    fetched_at="2026-11-09T05:00:00Z",
    ttl_days=180,
    license_note="HUD-USPS crosswalk. US government work.",
    byte_count=128,
)


def test_upsert_source_round_trip_and_replace(tmp_path: Path) -> None:
    conn = get_connection(tmp_path)
    try:
        upsert_source(conn, _ORIGINAL)
        assert get_source(conn, "hud_crosswalk") == _ORIGINAL
        assert get_source(conn, "missing") is None

        replacement = SourceRecord(
            source_id="hud_crosswalk",
            url="https://www.huduser.gov/portal/datasets/usps_crosswalk.html#q",
            as_of=None,
            fetched_at="2026-11-09T06:00:00Z",
            ttl_days=92,
            license_note="HUD-USPS crosswalk. US government work.",
            byte_count=None,
        )
        upsert_source(conn, replacement)
        assert get_source(conn, "hud_crosswalk") == replacement
    finally:
        conn.close()


def test_upsert_source_is_visible_from_a_new_connection(tmp_path: Path) -> None:
    first = get_connection(tmp_path)
    try:
        upsert_source(first, _ORIGINAL)
    finally:
        first.close()

    second = sqlite3.connect(tmp_path / "dce.sqlite")
    try:
        loaded = get_source(second, "hud_crosswalk")
        assert loaded == _ORIGINAL
    finally:
        second.close()
