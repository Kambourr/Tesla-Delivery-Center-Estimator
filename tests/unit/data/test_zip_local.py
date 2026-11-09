"""Per-ZIP local inputs. California uses stored CEC rows. Other states do not."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dce.data.zip_local import ZipLocalError, load_zip_local
from dce.storage.connection import get_connection
from dce.storage.repository import (
    OewsWageRecord,
    ZctaAcsRecord,
    ZevCountySalesRecord,
    ZevZipSalesRecord,
    ZipCbsaRecord,
    ZipCountyRecord,
    ZipZctaRecord,
    replace_zev_sales,
    replace_zip_geography,
    upsert_oews_wage,
    upsert_zcta_acs,
)


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path)
    replace_zip_geography(
        conn,
        (
            ZipCountyRecord("94402", "06081", "CA", 1.0, "San Mateo County", "2026-11-09"),
            ZipCountyRecord("10001", "36061", "NY", 1.0, "New York County", "2026-11-09"),
        ),
        (
            ZipCbsaRecord("94402", "41884", 1.0, "San Francisco-San Mateo-Redwood City, CA"),
            ZipCbsaRecord("10001", "35614", 1.0, "New York-Jersey City-White Plains, NY-NJ"),
        ),
        (ZipZctaRecord("94402", "94402", 1.0), ZipZctaRecord("10001", "10001", 1.0)),
    )
    upsert_zcta_acs(
        conn,
        ZctaAcsRecord("94402", 2024, 25475.0, 172522.0, None, None, None, households=10125.0),
    )
    upsert_oews_wage(
        conn,
        OewsWageRecord(
            "41860",
            "San Francisco-Oakland-Fremont, CA",
            "49-3023",
            "Automotive Service Technicians and Mechanics",
            75730.0,
            76030.0,
            "2025-05-01",
        ),
    )
    upsert_oews_wage(
        conn,
        OewsWageRecord(
            "00000",
            "United States",
            "49-3023",
            "Automotive Service Technicians and Mechanics",
            56420.0,
            50620.0,
            "2025-05-01",
        ),
    )
    replace_zev_sales(
        conn,
        (
            ZevZipSalesRecord("94402", "CA", 2025, 1, "Electric", 40, "2025-03-31", "cec"),
            ZevZipSalesRecord("94402", "CA", 2025, 1, "PHEV", 10, "2025-03-31", "cec"),
        ),
        (
            ZevCountySalesRecord(
                "San Mateo", "CA", 2025, 1, "Electric", "Tesla", 30, "2025-03-31", "cec"
            ),
            ZevCountySalesRecord(
                "San Mateo", "CA", 2025, 1, "Electric", "Other", 10, "2025-03-31", "cec"
            ),
        ),
    )
    return conn


def test_california_zip_uses_local_cec_and_parent_oews_wages(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        local = load_zip_local("94402", conn)
    finally:
        conn.close()
    assert local.geo.cbsa == "41884"
    assert local.oews_area == "41860"
    assert local.wage_basis == "cbsa"
    assert local.wages[0].mean_annual == 75730
    assert local.households == 10125
    assert local.ev.source == "cec"
    assert local.ev.ev_proxy is None
    assert local.ev.bev == 40
    assert local.ev.county_tesla_share == 0.75
    assert local.ev.tesla_bev_sales == 30


def test_non_california_zip_falls_back_without_inventing_tesla_sales(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        local = load_zip_local("10001", conn)
    finally:
        conn.close()
    assert local.geo.state == "NY"
    assert local.wage_basis == "national"
    assert local.oews_area == "00000"
    assert local.wages[0].mean_annual == 56420
    assert local.ev.source == "fallback"
    assert local.ev.ev_proxy == "acs_national_fallback"
    assert local.ev.tesla_bev_sales is None
    assert local.ev.bev is None


def test_unknown_zip_is_typed(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        try:
            load_zip_local("99999", conn)
            raise AssertionError("expected ZipLocalError")
        except ZipLocalError as exc:
            assert exc.zip_code == "99999"
    finally:
        conn.close()
