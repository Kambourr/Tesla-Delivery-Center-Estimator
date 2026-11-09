"""Round-trip the M2 fact tables."""

from __future__ import annotations

from pathlib import Path

from dce.storage.connection import get_connection
from dce.storage.repository import (
    EvZipRecord,
    OewsWageRecord,
    ZctaAcsRecord,
    get_ev_zip,
    get_oews_wage,
    get_zcta_acs,
    upsert_ev_zip,
    upsert_oews_wage,
    upsert_zcta_acs,
)


def test_public_rows_round_trip_and_replace(tmp_path: Path) -> None:
    conn = get_connection(tmp_path)
    try:
        acs = ZctaAcsRecord("94402", 2024, 25475.0, 172522.0, 18262.0, 26.2, 2000001.0)
        upsert_zcta_acs(conn, acs)
        assert get_zcta_acs(conn, "94402", 2024) == acs
        replaced = ZctaAcsRecord("94402", 2024, None, None, None, None, None)
        upsert_zcta_acs(conn, replaced)
        assert get_zcta_acs(conn, "94402", 2024) == replaced
        assert get_zcta_acs(conn, "94402", 2023) is None

        wage = OewsWageRecord(
            "41860",
            "San Francisco-Oakland-Fremont, CA",
            "49-3023",
            "Automotive Service Technicians and Mechanics",
            75730.0,
            76030.0,
            "2025-05-01",
        )
        upsert_oews_wage(conn, wage)
        assert get_oews_wage(conn, "41860", "49-3023", "2025-05-01") == wage

        ev = EvZipRecord("94402", "CA", 2257, 561, 4, 21403, "2024-12-31", "dmv")
        upsert_ev_zip(conn, ev)
        assert get_ev_zip(conn, "94402", "2024-12-31", "dmv") == ev
    finally:
        conn.close()
