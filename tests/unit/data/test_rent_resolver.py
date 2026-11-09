"""Rent chain uses each ZIP's own inputs. The Kidder headline stays on 41884."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dce.data.rent_resolver import resolve_rent
from dce.storage.connection import get_connection
from dce.storage.repository import (
    RentCbsaRecord,
    RentModelRecord,
    ZctaAcsRecord,
    ZctaCentroidRecord,
    ZipCbsaRecord,
    ZipCountyRecord,
    ZipZctaRecord,
    replace_rent_cbsa,
    replace_zip_geography,
    upsert_rent_model,
    upsert_zcta_acs,
    upsert_zcta_centroid,
)

_MODEL = {
    "model_id": "acs_rent_v1",
    "b_acs_rent": 1,
    "b_income": 0,
    "b_density": 0,
    "b_home_value": 0,
    "clamp_low": 0.5,
    "clamp_high": 2,
    "unit_sqft": 1000,
    "commercial_residential_ratio": 1,
}


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path)
    replace_zip_geography(
        conn,
        (
            ZipCountyRecord("94402", "06081", "CA", 1.0, "San Mateo County", "2026-11-09"),
            ZipCountyRecord("94401", "06081", "CA", 1.0, "San Mateo County", "2026-11-09"),
            ZipCountyRecord("94002", "06081", "CA", 1.0, "San Mateo County", "2026-11-09"),
            ZipCountyRecord("90001", "06037", "CA", 1.0, "Los Angeles County", "2026-11-09"),
            ZipCountyRecord("73301", "48453", "TX", 1.0, "Travis County", "2026-11-09"),
        ),
        (
            ZipCbsaRecord("94402", "41884", 1.0, "San Francisco-San Mateo-Redwood City, CA"),
            ZipCbsaRecord("94401", "41884", 1.0, "San Francisco-San Mateo-Redwood City, CA"),
            ZipCbsaRecord("94002", "99999", 1.0, "No industrial seed"),
            ZipCbsaRecord("90001", "31084", 1.0, "Los Angeles-Long Beach-Glendale, CA"),
            ZipCbsaRecord("73301", "12420", 1.0, "Austin-Round Rock-San Marcos, TX"),
        ),
        (
            ZipZctaRecord("94402", "94402", 1.0),
            ZipZctaRecord("94401", "94401", 1.0),
            ZipZctaRecord("94002", "94002", 1.0),
            ZipZctaRecord("90001", "90001", 1.0),
            ZipZctaRecord("73301", "73301", 1.0),
        ),
    )
    for zcta, rent in (("94402", 3501.0), ("94401", 1000.0), ("90001", 1400.0), ("73301", 1500.0)):
        upsert_zcta_acs(
            conn,
            ZctaAcsRecord(
                zcta,
                2024,
                1000.0,
                80000.0,
                None,
                None,
                500000.0,
                households=400.0,
                median_gross_rent=rent,
            ),
        )
        upsert_zcta_centroid(
            conn,
            ZctaCentroidRecord(zcta, 37.0, -122.0, "2024", "2024-01-01", land_sqmi=5.0),
        )
    replace_rent_cbsa(
        conn,
        (
            RentCbsaRecord(
                cbsa="41884",
                property_type="industrial",
                rent_psf_year=25.68,
                as_of="2026-09-30",
                citation="Kidder Mathews Q3 2026.",
                broker="Kidder Mathews",
                fetched_at="2026-11-09T00:00:00Z",
            ),
        ),
    )
    upsert_rent_model(
        conn,
        RentModelRecord(
            model_id="acs_rent_v1",
            formula_json=json.dumps(_MODEL),
            trained_on="Not fit to GSA.",
            as_of="2026-11-09",
        ),
    )
    return conn


def test_san_mateo_uses_the_cited_industrial_seed(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        resolved = resolve_rent("94402", conn)
    finally:
        conn.close()
    assert resolved.tier == "cbsa_raw"
    assert resolved.property_type == "industrial"
    assert resolved.rent_psf_year == pytest.approx(25.68)
    assert resolved.confidence == "high"
    assert "Kidder" in resolved.citation
    assert "Not scaled" in resolved.citation


def test_other_states_do_not_inherit_the_peninsula_headline(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        los_angeles = resolve_rent("90001", conn)
        austin = resolve_rent("73301", conn)
        cached = conn.execute(
            "SELECT components_json FROM rent_resolved_cache WHERE zip = '73301'"
        ).fetchone()
    finally:
        conn.close()
    assert los_angeles.tier == "acs_gross_rent"
    assert los_angeles.rent_psf_year == pytest.approx(16.8)
    assert los_angeles.property_type == "residential_proxy"
    assert los_angeles.confidence == "low"
    assert austin.rent_psf_year == pytest.approx(18.0)
    assert austin.rent_psf_year != pytest.approx(25.68)
    assert cached is not None
    components = json.loads(str(cached[0]))
    assert components["tier"] == "acs_gross_rent"
    assert components["monthly_rent"] == 1500.0


def test_missing_zcta_rent_uses_the_county_median(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        resolved = resolve_rent("94002", conn)
    finally:
        conn.close()
    assert resolved.tier == "acs_gross_rent_county"
    assert resolved.confidence == "low"
    assert resolved.rent_psf_year == pytest.approx((3501.0 + 1000.0) / 2 * 12 / 1000)
