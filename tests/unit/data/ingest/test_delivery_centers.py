"""Committed US Tesla delivery-center snapshot. No network."""

from __future__ import annotations

import csv
from collections import Counter
from itertools import combinations

import pytest

from dce.data.ingest.delivery_centers import (
    CONFIDENCE_LEVELS,
    SNAPSHOT_AS_OF,
    DeliveryCenter,
    DeliveryCenterError,
    bay_area_snapshot_path,
    delivery_center_citation_url,
    load_delivery_centers,
    parse_delivery_centers,
    snapshot_path,
)
from dce.geo.catchment import straight_line_miles

_HEADER = (
    "center_id,name,address,city,state,zip,lat,lon,location_type,as_of,"
    "coordinate_basis,source,confidence\n"
)
_COLMA = (
    "colma,Tesla,1500 Collins Ave,Colma,CA,94014,37.6,-122.4,delivery,2026-11-08,"
    "census,dce_research_20261108,high\n"
)
_BAY_AREA_IDS = {
    "colma",
    "sunnyvale",
    "fremont-factory",
    "dublin",
    "corte-madera",
    "los-gatos",
    "vallejo",
    "gilroy",
    "santa-rosa",
    "san-jose-hub",
}
# (lat_min, lat_max, lon_min, lon_max): lower 48, Alaska, Hawaii.
_US_BOXES = (
    (24.3, 49.5, -125.0, -66.9),
    (51.0, 71.6, -180.0, -129.9),
    (18.8, 22.4, -160.4, -154.7),
)
_KNOWN_SOURCES = {
    "dce_research_20261108",
    "tesla_findus_wayback_20241214",
    "alltheplaces_tesla_20261017",
    "osm_overpass_20261108",
}


def _in_us(row: DeliveryCenter) -> bool:
    return any(
        lat_min <= row.lat <= lat_max and lon_min <= row.lon <= lon_max
        for lat_min, lat_max, lon_min, lon_max in _US_BOXES
    )


def test_us_snapshot_sanity() -> None:
    rows = load_delivery_centers()
    assert snapshot_path().name == "tesla_delivery_centers_us_2026-11-08.csv"
    # Row count: 118 on the 2024-12-14 list, plus Los Gatos, Santa Rosa,
    # the San Jose hub, and two possible handovers. Allow a rebuild some room.
    assert 110 <= len(rows) <= 200
    delivery = [row for row in rows if row.location_type == "delivery"]
    assert len(delivery) >= 110
    states = Counter(row.state for row in rows)
    assert len(states) >= 25
    assert {"CA", "FL", "NY", "TX", "WA", "IL", "AZ", "CO", "GA", "HI"} <= set(states)
    assert states["CA"] >= 25
    coordinates = Counter((round(row.lat, 5), round(row.lon, 5)) for row in rows)
    assert [point for point, count in coordinates.items() if count > 1] == []
    # No two rows within 1 km: a near-duplicate would be the same site geocoded twice.
    close = [
        (a.center_id, b.center_id)
        for a, b in combinations(rows, 2)
        if straight_line_miles(a.lat, a.lon, b.lat, b.lon) < 0.62
    ]
    assert close == []
    addresses = Counter((row.address.lower(), row.zip_code) for row in rows)
    assert [key for key, count in addresses.items() if count > 1] == []
    outside = [row.center_id for row in rows if not _in_us(row)]
    assert outside == []
    hawaii = [row for row in rows if row.state == "HI"]
    assert all(18.8 <= row.lat <= 22.4 for row in hawaii)
    assert {row.as_of for row in rows} == {SNAPSHOT_AS_OF}


def test_every_row_names_its_sources_and_confidence() -> None:
    rows = load_delivery_centers()
    for row in rows:
        assert row.confidence in CONFIDENCE_LEVELS
        assert set(row.sources) <= _KNOWN_SOURCES, row.center_id
        if row.location_type == "delivery" and row.center_id not in _BAY_AREA_IDS:
            assert row.sources[0] == "tesla_findus_wayback_20241214", row.center_id
        if row.location_type == "possible_handover":
            assert row.confidence == "low"
            assert "tesla_findus_wayback_20241214" not in row.sources
    # Texas had no centers on the live list on 2026-11-08 (research section 1.1).
    assert {row.confidence for row in rows if row.state == "TX"} == {"low"}
    levels = Counter(row.confidence for row in rows)
    assert levels["high"] > levels["medium"] + levels["low"]
    assert levels["low"] >= 1
    assert "web.archive.org" in delivery_center_citation_url()


def test_bay_area_research_rows_are_carried_over_unchanged() -> None:
    by_id = {row.center_id: row for row in load_delivery_centers()}
    lines = [
        line
        for line in bay_area_snapshot_path().read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    research = list(csv.DictReader(lines))
    assert {row["center_id"] for row in research} == _BAY_AREA_IDS
    for raw in research:
        row = by_id[raw["center_id"]]
        assert (row.name, row.address, row.city, row.state, row.zip_code) == (
            raw["name"],
            raw["address"],
            raw["city"],
            raw["state"],
            raw["zip"],
        )
        assert (row.lat, row.lon) == (float(raw["lat"]), float(raw["lon"]))
        assert row.location_type == raw["location_type"]
        assert row.coordinate_basis == raw["coordinate_basis"] == "census_gazetteer_2024_zcta"
        assert row.sources[0] == "dce_research_20261108"
    assert by_id["san-jose-hub"].location_type == "hub"
    assert by_id["san-jose-hub"].confidence == "medium"
    colma = by_id["colma"]
    assert colma.confidence == "high"
    # Census 2024 ZCTA internal points: 94402 to 94014 is the research 12.2 miles.
    miles = straight_line_miles(37.540103, -122.330103, colma.lat, colma.lon)
    assert miles == pytest.approx(12.23, abs=0.02)


def test_new_rows_outside_the_bay_area() -> None:
    by_id = {row.center_id: row for row in load_delivery_centers()}
    seaside = by_id["seaside-ca"]
    assert seaside.address == "1901 Del Monte Blvd"
    assert seaside.location_type == "delivery"
    assert seaside.coordinate_basis == "census_geocoder_current"
    austin = by_id["austin-tx"]
    assert austin.coordinate_basis == "alltheplaces_findus_point"
    plano = by_id["plano-tx"]
    assert plano.location_type == "possible_handover"
    assert plano.sources == ("alltheplaces_tesla_20261017",)


def test_snapshot_rejects_a_bad_row() -> None:
    with pytest.raises(DeliveryCenterError, match="more than once"):
        parse_delivery_centers(_HEADER + _COLMA + _COLMA)
    with pytest.raises(DeliveryCenterError, match="location_type"):
        parse_delivery_centers(_HEADER + _COLMA.replace(",delivery,", ",showroom,"))
    with pytest.raises(DeliveryCenterError, match="confidence"):
        parse_delivery_centers(_HEADER + _COLMA.replace(",high", ",certain"))
    with pytest.raises(DeliveryCenterError, match="source"):
        parse_delivery_centers(_HEADER + _COLMA.replace("dce_research_20261108", "Tesla HQ"))
    with pytest.raises(DeliveryCenterError, match="source must be a non-empty"):
        parse_delivery_centers(_HEADER + _COLMA.replace("dce_research_20261108", ""))


def test_the_bay_area_research_file_lacks_the_new_columns() -> None:
    with pytest.raises(DeliveryCenterError, match="missing columns: source, confidence"):
        load_delivery_centers(bay_area_snapshot_path())


def test_parsed_row_exposes_sources_in_order() -> None:
    text = _HEADER + _COLMA.replace(
        "dce_research_20261108", "tesla_findus_wayback_20241214;osm_overpass_20261108"
    )
    (row,) = parse_delivery_centers(text)
    assert row.sources == ("tesla_findus_wayback_20241214", "osm_overpass_20261108")
    assert row.confidence == "high"
