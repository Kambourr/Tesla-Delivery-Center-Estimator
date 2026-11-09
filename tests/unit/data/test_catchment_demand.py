"""Catchment demand: county anchor, handover factor, and the non-California fallback.

Households in the fallback come from the ACS fixture. No network.
"""

from __future__ import annotations

import pytest

from dce.data.catchment_demand import (
    NATIONAL_TESLA_EV_SHARE,
    CatchmentDemandError,
    bay_area_zip_demand,
    build_catchment_demand,
    delivery_center_sites,
    non_california_zip_demand,
)
from dce.data.ingest.census_acs import ZctaAcs
from dce.data.ingest.delivery_centers import load_delivery_centers
from dce.geo.catchment import CenterSite, catchment_features
from dce.geo.resolve import resolve_zip
from dce.model.types import GeoContext

_TX = GeoContext(zip_code="10001", zcta="10001", county_fips="36061", cbsa="35620", state="TX")


def _acs(zcta: str, households: float | None, income: float | None = 80_000.0) -> ZctaAcs:
    return ZctaAcs(
        zcta=zcta,
        year=2024,
        population=1_000.0,
        median_hh_income=income,
        vehicles_available=400.0,
        mean_commute=30.0,
        median_home_value=400_000.0,
        households=households,
    )


def test_non_california_fallback_weights_by_acs_households() -> None:
    acs = (_acs("10001", 100), _acs("10002", 300), _acs("10003", None))
    demand = non_california_zip_demand(
        1_000.0,
        acs,
        ev_stock_by_zip={"10001": 30.0, "10002": 30.0, "10003": 30.0},
        total_ldv_by_zip={"10001": 1_000.0, "10002": 1_000.0, "10003": 1_000.0},
        centroids={
            "10001": (40.75, -73.99),
            "10002": (40.72, -73.98),
            "10003": (40.73, -73.99),
        },
    )
    by_zip = {row.zip_code: row.deliveries_per_year for row in demand}
    assert "10003" not in by_zip
    assert by_zip["10002"] == pytest.approx(3 * by_zip["10001"])
    assert sum(by_zip.values()) == pytest.approx(1_000.0)


def test_build_catchment_demand_uses_the_fallback_outside_california() -> None:
    acs = (_acs("10001", 100), _acs("10002", 100))
    demand = build_catchment_demand(
        _TX,
        state_tesla_volume=500.0,
        acs_rows=acs,
        ev_stock_by_zip={"10001": 10.0, "10002": 10.0},
        total_ldv_by_zip={"10001": 1_000.0, "10002": 1_000.0},
        centroids={"10001": (40.75, -73.99), "10002": (40.72, -73.98)},
    )
    assert {row.zip_code for row in demand} == {"10001", "10002"}
    assert sum(row.deliveries_per_year or 0.0 for row in demand) == pytest.approx(500.0)
    with pytest.raises(CatchmentDemandError, match="outside California"):
        build_catchment_demand(_TX)


def test_non_california_ev_registrations_use_the_national_tesla_share() -> None:
    acs = (_acs("10001", 100), _acs("10002", 100))
    demand = build_catchment_demand(
        _TX,
        state_ev_registrations=1_000.0,
        acs_rows=acs,
        ev_stock_by_zip={"10001": 10.0, "10002": 10.0},
        total_ldv_by_zip={"10001": 1_000.0, "10002": 1_000.0},
        centroids={"10001": (40.75, -73.99), "10002": (40.72, -73.98)},
    )
    assert sum(row.deliveries_per_year or 0.0 for row in demand) == pytest.approx(
        1_000.0 * NATIONAL_TESLA_EV_SHARE
    )
    assert NATIONAL_TESLA_EV_SHARE == pytest.approx(0.462)


def test_handover_factor_scales_the_non_california_allocation() -> None:
    acs = (_acs("10001", 100),)
    demand = build_catchment_demand(
        _TX,
        state_tesla_volume=500.0,
        handover_factor=1.10,
        acs_rows=acs,
        ev_stock_by_zip={"10001": 10.0},
        total_ldv_by_zip={"10001": 1_000.0},
        centroids={"10001": (40.75, -73.99)},
    )
    assert demand[0].deliveries_per_year == pytest.approx(550.0)


def test_county_anchor_on_the_research_centers_matches_the_calibration_note() -> None:
    """demand_calibration.md low case: county totals, H = 1.00, nine Bay Area centers."""
    geo = resolve_zip("94402")
    centers = tuple(
        CenterSite(row.center_id, row.name, row.lat, row.lon)
        for row in load_delivery_centers()
        if row.location_type == "delivery"
    )
    low = catchment_features(geo, centers, bay_area_zip_demand(handover_factor=1.00))
    base = catchment_features(geo, centers, bay_area_zip_demand(handover_factor=1.10))
    assert low.gravity.total_deliveries_per_year == pytest.approx(5318, abs=1)
    assert low.nearest.total_deliveries_per_year == pytest.approx(3990, abs=1)
    assert base.gravity.total_deliveries_per_year == pytest.approx(5849, abs=1)
    assert base.nearest.total_deliveries_per_year == pytest.approx(4389, abs=1)


def test_estimate_sites_are_the_us_delivery_list_not_the_research_ten() -> None:
    sites = delivery_center_sites()
    ids = {site.center_id for site in sites}
    assert len(sites) >= 110
    assert {"stockton-ca", "seaside-ca", "sacramento-ca", "colma"} <= ids
    assert "san-jose-hub" not in ids
    uniform = bay_area_zip_demand(handover_factor=1.0, county_anchor=False)
    gravity = catchment_features(resolve_zip("94402"), sites, uniform).gravity
    # DATA_SOURCES §10: national delivery list, before this calibration.
    assert gravity.total_deliveries_per_year == pytest.approx(5483.3, abs=0.1)


def test_us_list_handover_cases_for_94402() -> None:
    """County anchor times H, on the US delivery list. Base is what estimate uses."""
    geo = resolve_zip("94402")
    sites = delivery_center_sites()
    expected = {1.00: (5280.3, 3990.2), 1.10: (5808.3, 4389.2), 1.30: (6864.4, 5187.2)}
    for factor, (gravity, nearest) in expected.items():
        features = catchment_features(geo, sites, bay_area_zip_demand(handover_factor=factor))
        assert features.gravity.total_deliveries_per_year == pytest.approx(gravity, abs=0.1)
        assert features.nearest.total_deliveries_per_year == pytest.approx(nearest, abs=0.1)
