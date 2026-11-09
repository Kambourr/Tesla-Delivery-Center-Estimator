"""``scripts/build_us_delivery_centers.py`` on committed fixtures. No network."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from dce.data.ingest.delivery_centers import parse_delivery_centers

_ROOT = Path(__file__).resolve().parents[4]
_FIXTURES = _ROOT / "tests" / "fixtures" / "delivery_centers"


def _load_script() -> ModuleType:
    path = _ROOT / "scripts" / "build_us_delivery_centers.py"
    spec = importlib.util.spec_from_file_location("build_us_delivery_centers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build = _load_script()


def _inputs() -> tuple[Any, Any, Any, Any]:
    """Return ``(findus, points, atp, osm)`` parsed from the fixtures."""
    findus = build.parse_findus_list((_FIXTURES / "findus_list_sample.html").read_text("utf-8"))
    atp = build.parse_atp((_FIXTURES / "atp_tesla_sample.geojson").read_text("utf-8"))
    osm = build.parse_overpass((_FIXTURES / "overpass_sample.json").read_text("utf-8"))
    census = build.parse_census_batch((_FIXTURES / "census_batch_sample.csv").read_text("utf-8"))
    return findus, build.first_points(findus, census, atp), atp, osm


def _bay_area() -> list[dict[str, str]]:
    return list(build.read_bay_area(_FIXTURES / "bay_area_sample.csv"))


def test_host_allowlist_is_exactly_the_public_sources() -> None:
    assert build.ALLOWED_HOSTS == {
        "web.archive.org",
        "alltheplaces-data.openaddresses.io",
        "overpass-api.de",
        "geocoding.geo.census.gov",
        "nominatim.openstreetmap.org",
    }
    for url in (
        build.FINDUS_URL,
        build.ATP_URL,
        build.OVERPASS_URL,
        build.CENSUS_BATCH_URL,
        build.NOMINATIM_URL,
    ):
        build.require_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tesla.com/findus/list/deliverycenters/United+States",
        "http://web.archive.org/web/2024/https://www.tesla.com/",
        "https://web.archive.org.example.com/x",
        "https://user:secret@overpass-api.de/api/interpreter",
        "https://www.loopnet.com/",
        "file:///etc/passwd",
    ],
)
def test_off_allowlist_urls_are_refused_before_any_request(url: str) -> None:
    with pytest.raises(build.BuildError):
        build.require_allowed(url)
    with pytest.raises(build.BuildError):
        build.fetch(url)


def test_findus_list_parses_and_cleans_addresses() -> None:
    findus, _, _, _ = _inputs()
    assert len(findus) == 8
    by_slug = {row.slug: row for row in findus}
    seaside = by_slug["montereyseaside"]
    assert (seaside.street, seaside.city, seaside.zip_code) == (
        "1901 Del Monte Blvd",
        "Seaside",
        "93955",
    )
    assert by_slug["15328"].street == "1800 E Spring St"
    assert Counter(row.state for row in findus) == {"CA": 4, "NC": 3, "TX": 1}


def test_findus_parser_rejects_a_page_without_centers() -> None:
    with pytest.raises(build.BuildError, match="no state headers"):
        build.parse_findus_list("<html><body>Access denied</body></html>")


def test_census_batch_matches_seven_of_eight_as_lat_lon() -> None:
    census = build.parse_census_batch((_FIXTURES / "census_batch_sample.csv").read_text("utf-8"))
    assert sorted(census) == [0, 1, 2, 3, 4, 5, 6]
    lat, lon = census[3]
    assert lat == pytest.approx(36.616749815725)
    assert lon == pytest.approx(-121.843636059828)


def test_census_batch_body_lists_every_address() -> None:
    findus, _, _, _ = _inputs()
    body = build.census_batch_body(findus, "b0undary").decode("utf-8")
    assert 'name="benchmark"' in body and "Public_AR_Current" in body
    for index, row in enumerate(findus):
        assert f"{index},{row.street}" in body or f'{index},"{row.street}"' in body


def test_build_rows_confidence_rules_and_no_invented_rows() -> None:
    findus, points, atp, osm = _inputs()
    rows, notes = build.build_rows(findus, points, atp, osm, _bay_area())
    by_id = {row.center_id: row for row in rows}
    assert set(by_id) == {
        "colma",
        "san-jose-hub",
        "bakersfield-ca",
        "long-beach-ca",
        "seaside-ca",
        "matthews-nc",
        "raleigh-nc",
        "charlotte-nc",
        "austin-tx",
        "manhasset-ny",
        "plano-tx",
    }
    # Bay Area research rows are carried over with their ZCTA points.
    colma = by_id["colma"]
    assert (colma.lat, colma.lon) == (37.690689, -122.447721)
    assert colma.source == "dce_research_20261108;tesla_findus_wayback_20241214"
    assert colma.confidence == "high"
    assert by_id["san-jose-hub"].confidence == "medium"
    # On the list and in the 2026 All the Places run.
    assert by_id["seaside-ca"].confidence == "high"
    assert by_id["seaside-ca"].coordinate_basis == "census_geocoder_current"
    # On the list, not in All the Places, but OSM has the shop.
    assert by_id["bakersfield-ca"].confidence == "medium"
    assert by_id["bakersfield-ca"].source == "tesla_findus_wayback_20241214;osm_overpass_20261108"
    # On the list with no 2026 evidence.
    assert by_id["long-beach-ca"].confidence == "low"
    assert by_id["charlotte-nc"].confidence == "low"
    # Texas had no live-list centers on 2026-11-08, so Austin is capped at low.
    austin = by_id["austin-tx"]
    assert austin.confidence == "low"
    assert austin.coordinate_basis == "alltheplaces_findus_point"
    assert any("austinpondsprings" in note for note in notes)
    # Delivery-named All the Places sites that are not on the list.
    for center_id in ("manhasset-ny", "plano-tx"):
        assert by_id[center_id].location_type == "possible_handover"
        assert by_id[center_id].confidence == "low"
        assert "tesla_findus_wayback_20241214" not in by_id[center_id].source
    # Every address comes from an input. Nothing is made up.
    known = {row.street for row in findus} | {site.street for site in atp}
    known |= {row["address"] for row in _bay_area()}
    assert {row.address for row in rows} <= known


def test_row_without_any_geocode_is_dropped_not_guessed() -> None:
    findus, points, atp, osm = _inputs()
    long_beach = next(i for i, row in enumerate(findus) if row.slug == "15328")
    del points[long_beach]
    rows, notes = build.build_rows(findus, points, atp, osm, _bay_area())
    assert "long-beach-ca" not in {row.center_id for row in rows}
    assert any(note.startswith("dropped 15328") for note in notes)


def test_rendered_csv_loads_with_the_package_loader() -> None:
    findus, points, atp, osm = _inputs()
    rows, _ = build.build_rows(findus, points, atp, osm, _bay_area())
    text = build.render_csv(rows)
    assert text.startswith("# US Tesla delivery locations.")
    assert "DATA_SOURCES.md section 10" in text
    loaded = parse_delivery_centers(text)
    assert [row.center_id for row in loaded] == [row.center_id for row in rows]


def test_main_rebuilds_from_cache_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    names = {
        "findus_list_sample.html": "findus_wayback_20241214.html",
        "atp_tesla_sample.geojson": f"atp_tesla_{build.ATP_RUN}.geojson",
        "overpass_sample.json": "overpass_tesla_shops.json",
        "census_batch_sample.csv": f"census_batch_{build.FINDUS_CAPTURE}.csv",
    }
    for fixture, cached_name in names.items():
        shutil.copy(_FIXTURES / fixture, cache / cached_name)

    def no_network(url: str, **_: object) -> bytes:
        raise AssertionError(f"unexpected network call to {url}")

    monkeypatch.setattr(build, "fetch", no_network)
    out = tmp_path / "centers.csv"
    assert build.main(["--cache-dir", str(cache), "--out", str(out)]) == 0
    loaded = parse_delivery_centers(out.read_text("utf-8"))
    # Ten Bay Area seed rows, seven non-Bay Area list rows, two possible handovers.
    assert len(loaded) == 19
    assert "Wrote 19 rows" in capsys.readouterr().out
