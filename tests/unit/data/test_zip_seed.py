"""The committed nationwide seed loads offline and stays local to each ZIP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dce.data.rent_resolver import resolve_rent
from dce.data.zip_local import load_zip_local
from dce.data.zip_seed import load_zip_seed
from dce.geo.resolve import resolve_zip
from dce.storage.connection import get_connection

_ROOT = Path(__file__).resolve().parents[3]
_BAY = _ROOT / "data" / "geo" / "zcta_bay_area.geojson"


def test_bay_area_fixture_is_a_small_click_layer() -> None:
    payload = json.loads(_BAY.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert "crs" not in payload
    assert _BAY.stat().st_size < 1_000_000
    codes = {feature["properties"]["zcta"] for feature in payload["features"]}
    assert "94402" in codes
    assert len(codes) == 300


def test_bundled_seed_keeps_94402_and_does_not_export_peninsula_rent(tmp_path: Path) -> None:
    conn = get_connection(tmp_path)
    try:
        counts = load_zip_seed(conn, fetched_at="2026-11-09T00:00:00Z")
        assert counts.centroids == 33791
        assert counts.crosswalk_rows == 54196
        local = load_zip_local("94402", conn)
        assert local.geo == resolve_zip("94402")
        assert local.population == 25475
        assert local.households == 10125
        assert local.median_hh_income == 172522
        assert local.median_gross_rent == 3501
        assert local.lat == pytest.approx(37.540103)
        assert local.oews_area == "41860"
        assert local.wage_basis == "cbsa"
        assert local.ev.source == "cec"
        assert local.ev.tesla_bev_sales is not None
        assert local.rent is not None
        assert local.rent.tier == "zip_adjusted_cbsa"
        assert "Kidder" in local.rent.citation
        austin = resolve_rent("73301", conn)
    finally:
        conn.close()
    assert austin.property_type == "residential_proxy"
    assert austin.tier == "acs_gross_rent"
    assert austin.rent_psf_year != pytest.approx(25.68)
