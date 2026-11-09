"""Committed Tesla delivery-center snapshot. No network."""

from __future__ import annotations

import pytest

from dce.data.ingest.delivery_centers import (
    SNAPSHOT_AS_OF,
    DeliveryCenterError,
    load_delivery_centers,
    parse_delivery_centers,
)
from dce.geo.catchment import straight_line_miles


def test_snapshot_has_the_bay_area_delivery_list_and_the_san_jose_hub() -> None:
    rows = load_delivery_centers()
    by_id = {row.center_id: row for row in rows}
    delivery = [row for row in rows if row.location_type == "delivery"]
    assert len(delivery) == 9
    assert by_id["san-jose-hub"].location_type == "hub"
    assert by_id["san-jose-hub"].zip_code == "95131"
    colma = by_id["colma"]
    assert colma.as_of == SNAPSHOT_AS_OF
    assert colma.address == "1500 Collins Ave"
    assert colma.zip_code == "94014"
    assert colma.coordinate_basis == "census_gazetteer_2024_zcta"
    # Census 2024 ZCTA internal points: 94402 to 94014 is the research 12.2 miles.
    miles = straight_line_miles(37.540103, -122.330103, colma.lat, colma.lon)
    assert miles == pytest.approx(12.23, abs=0.02)


def test_snapshot_rejects_a_bad_row() -> None:
    text = (
        "center_id,name,address,city,state,zip,lat,lon,location_type,as_of,coordinate_basis\n"
        "colma,Tesla,1500 Collins Ave,Colma,CA,94014,37.6,-122.4,delivery,2026-11-08,census\n"
        "colma,Tesla,1500 Collins Ave,Colma,CA,94014,37.6,-122.4,delivery,2026-11-08,census\n"
    )
    with pytest.raises(DeliveryCenterError, match="more than once"):
        parse_delivery_centers(text)
    with pytest.raises(DeliveryCenterError, match="location_type"):
        parse_delivery_centers(
            "center_id,name,address,city,state,zip,lat,lon,location_type,as_of,coordinate_basis\n"
            "x,N,A,C,CA,94014,37.6,-122.4,showroom,2026-11-08,census\n"
        )
