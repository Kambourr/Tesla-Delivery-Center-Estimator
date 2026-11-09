"""Non-California demand fallback. Households come from the ACS fixture. No network."""

from __future__ import annotations

import pytest

from dce.data.catchment_demand import (
    CatchmentDemandError,
    build_catchment_demand,
    non_california_zip_demand,
)
from dce.data.ingest.census_acs import ZctaAcs
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
