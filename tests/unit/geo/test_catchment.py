"""San Mateo catchment against the 2026-11-08 research figures. No network."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dce.data.ingest.delivery_centers import load_delivery_centers
from dce.geo.catchment import (
    DRIVE_CIRCUITY,
    MAX_DRIVE_MILES,
    CatchmentDataError,
    CenterSite,
    ZipDemand,
    catchment_features,
    drive_distance_miles,
)
from dce.model.types import GeoContext

# 2025 CEC county sheet, 9-county Bay Area: Tesla Electric 49,704 / Electric 94,131.
_BAY_TESLA_BEV_RATIO = 49704 / 94131
_FIXTURE = (
    Path(__file__).resolve().parents[3] / "data" / "demo" / "san_mateo" / "catchment_bev_2025.csv"
)
_GEO = GeoContext(
    zip_code="94402",
    zcta="94402",
    county_fips="06081",
    cbsa="41884",
    state="CA",
)


def test_san_mateo_94402_matches_the_research_catchment() -> None:
    result = catchment_features(_GEO, _bay_area_centers(), _bay_area_demand(), beta=2)
    nearest = result.nearest.total_deliveries_per_year
    gravity = result.gravity.total_deliveries_per_year
    # Research §4.4: 4,370 nearest-center deliveries over 20 ZCTAs, and Huff
    # beta 2 "about 5,720". The reproducible gravity total on this fixture,
    # with the ADR-0004 60-mile drive cap and all nine delivery centers, is
    # 5,523. The cap, the centroids, and rounding 49,704/94,131 to 0.528 do
    # not close that gap (see the catchment module docstring and STATUS).
    assert nearest == pytest.approx(4370, abs=1)
    assert gravity == pytest.approx(5522.8, abs=1)
    assert len(result.nearest.zips) == 20
    assert result.gravity.beta == 2
    assert result.nearest.beta is None
    assert result.beta == 2
    taken = result.nearest.taken_from
    assert [row.center_id for row in taken[:2]] == ["colma", "sunnyvale"]
    top_two = taken[0].deliveries_per_year + taken[1].deliveries_per_year
    assert top_two > 0.8 * nearest
    mean_miles = sum(row.straight_line_miles for row in result.nearest.zips) / len(
        result.nearest.zips
    )
    assert mean_miles == pytest.approx(6.6, abs=0.3)
    other = next(row for row in result.nearest.zips if row.zip_code != "94402")
    assert other.drive_miles == pytest.approx(other.straight_line_miles * DRIVE_CIRCUITY)
    assert other.drive_miles <= MAX_DRIVE_MILES
    # Steeper distance decay assigns the candidate less of the surrounding ZIPs.
    low = catchment_features(_GEO, _bay_area_centers(), _bay_area_demand(), beta=1.5)
    high = catchment_features(_GEO, _bay_area_centers(), _bay_area_demand(), beta=3)
    assert high.gravity.total_deliveries_per_year < gravity < low.gravity.total_deliveries_per_year


def test_no_existing_center_nearby_keeps_local_demand_and_takes_nothing() -> None:
    demand = (
        ZipDemand("94402", 37.54, -122.33, 100),
        ZipDemand("94403", 37.55, -122.32, 40),
        ZipDemand("94105", 40.5, -122.33, 999),
    )
    far = (CenterSite("remote", "Remote", 45.0, -122.33),)
    result = catchment_features(_GEO, far, demand)
    assert result.nearest.total_deliveries_per_year == pytest.approx(140)
    assert result.gravity.total_deliveries_per_year == pytest.approx(140)
    assert result.nearest.taken_from == ()
    assert result.gravity.taken_from == ()
    assert {row.zip_code for row in result.nearest.zips} == {"94402", "94403"}
    empty = catchment_features(_GEO, (), demand, radius_miles=15)
    assert {row.zip_code for row in empty.nearest.zips} == {"94402", "94403"}
    assert empty.nearest.taken_from == ()


def test_a_zip_with_no_data_is_skipped_and_a_missing_candidate_errors() -> None:
    demand = (
        ZipDemand("94402", 37.54, -122.33, 80),
        ZipDemand("94401", None, None, None),
        ZipDemand("94404", 37.56, -122.31, None),
    )
    result = catchment_features(_GEO, (), demand)
    assert [row.zip_code for row in result.nearest.zips] == ["94402"]
    assert result.nearest.total_deliveries_per_year == pytest.approx(80)
    with pytest.raises(CatchmentDataError, match="no catchment data"):
        catchment_features(_GEO, (), (ZipDemand("94402", None, -122.33, 10),))
    with pytest.raises(CatchmentDataError, match="beta"):
        catchment_features(_GEO, (), demand, beta=0)


def test_drive_proxy_is_straight_line_times_circuity() -> None:
    assert drive_distance_miles(40) == pytest.approx(50)
    assert DRIVE_CIRCUITY == 1.25
    assert MAX_DRIVE_MILES == 60


def _bay_area_centers() -> tuple[CenterSite, ...]:
    return tuple(
        CenterSite(row.center_id, row.name, row.lat, row.lon)
        for row in load_delivery_centers()
        if row.location_type == "delivery"
    )


def _bay_area_demand() -> tuple[ZipDemand, ...]:
    rows: list[ZipDemand] = []
    with _FIXTURE.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                ZipDemand(
                    record["zip"],
                    float(record["lat"]),
                    float(record["lon"]),
                    int(record["bev_2025"]) * _BAY_TESLA_BEV_RATIO,
                )
            )
    return tuple(rows)
