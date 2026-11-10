"""Broker market-report rents: the cited seed, its unit conversion, and the resolver tiers."""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

import pytest

from dce.config import bundled_seed_dir
from dce.data.rent_defaults import (
    GROSS_TO_NNN_LOAD,
    RentSeedError,
    nnn_rent_psf_year,
    read_rent_market_seed,
    read_rent_seed,
)
from dce.data.rent_resolver import resolve_rent
from dce.data.zip_seed import sync_rent_market
from dce.storage.connection import get_connection
from dce.storage.repository import (
    RentCbsaRecord,
    ZctaAcsRecord,
    ZipCbsaRecord,
    ZipCountyRecord,
    ZipZctaRecord,
    get_source,
    list_rent_market,
    replace_rent_cbsa,
    replace_zip_geography,
    upsert_zcta_acs,
)

_SEED = bundled_seed_dir() / "rent_market.csv"
_BROKERS = {"CBRE", "Cushman & Wakefield", "Colliers", "JLL", "Newmark"}
_FIELDS = (
    "geography_level",
    "geography_id",
    "market",
    "submarket",
    "property_type",
    "rent_psf_year",
    "reported_rent",
    "reported_unit",
    "reported_basis",
    "source",
    "report",
    "quarter",
    "as_of",
    "url",
    "note",
)

# Metros the seed must cover: CBSA or metro-division codes from the shipped crosswalk.
_REQUIRED_CBSAS = {
    "31084": "Los Angeles",
    "36084": "Oakland (East Bay)",
    "41940": "San Jose (Silicon Valley)",
    "42644": "Seattle",
    "14454": "Boston",
    "11694": "Washington DC (Northern Virginia)",
    "47764": "Washington DC",
    "16984": "Chicago",
    "33124": "Miami",
    "12420": "Austin",
    "19124": "Dallas",
    "23104": "Fort Worth",
    "26420": "Houston",
    "38060": "Phoenix",
    "19740": "Denver",
    "12054": "Atlanta",
}
_REQUIRED_COUNTIES = {
    "36061": "Manhattan",
    "36047": "Brooklyn",
    "36081": "Queens",
    "36005": "Bronx",
    "34003": "Bergen",
    "34017": "Hudson",
    "34013": "Essex",
}


def test_monthly_and_gross_figures_convert_to_annual_nnn() -> None:
    assert nnn_rent_psf_year(1.33, "usd_psf_month", "nnn") == pytest.approx(15.96)
    assert nnn_rent_psf_year(25.15, "usd_psf_year", "nnn") == pytest.approx(25.15)
    assert GROSS_TO_NNN_LOAD == pytest.approx(0.15)
    assert nnn_rent_psf_year(74.37, "usd_psf_year", "full_service_gross") == pytest.approx(
        74.37 / 1.15
    )
    assert nnn_rent_psf_year(2.0, "usd_psf_month", "full_service_gross") == pytest.approx(
        24.0 / 1.15
    )
    with pytest.raises(RentSeedError):
        nnn_rent_psf_year(1.0, "usd_psf_week", "nnn")
    with pytest.raises(RentSeedError):
        nnn_rent_psf_year(1.0, "usd_psf_year", "modified_gross")


def test_conversion_matches_the_shipped_assumptions_opex_load() -> None:
    text = (bundled_seed_dir().parent / "defaults" / "assumptions.yaml").read_text("utf-8")
    assert "  opex_load: 0.15\n" in text


def test_shipped_seed_is_cited_converted_and_covers_the_required_metros() -> None:
    rows = read_rent_market_seed(_SEED)
    with _SEED.open(encoding="utf-8") as handle:
        assert tuple(csv.DictReader(handle).fieldnames or ()) == _FIELDS
    by_key = {(row.geography_level, row.geography_id): row for row in rows}
    assert len(by_key) == len(rows) == 50
    for code in _REQUIRED_CBSAS:
        assert ("cbsa", code) in by_key, _REQUIRED_CBSAS[code]
    for code in _REQUIRED_COUNTIES:
        assert ("county", code) in by_key, _REQUIRED_COUNTIES[code]
    for row in rows:
        assert row.source in _BROKERS
        assert row.url.startswith("https://")
        assert row.quarter == "2026Q3"
        assert row.as_of == "2026-09-30"
        assert row.report.endswith("Q3 2026")
        assert row.rent_psf_year == pytest.approx(
            nnn_rent_psf_year(row.reported_rent, row.reported_unit, row.reported_basis),
            abs=0.005,
        )
        # Industrial and flex asking rents in these reports sit between $5 and $70 a year.
        assert 5.0 < row.rent_psf_year < 70.0
    manhattan = by_key[("county", "36061")]
    assert manhattan.property_type == "office_showroom_proxy"
    assert manhattan.reported_basis == "full_service_gross"
    assert manhattan.reported_rent == pytest.approx(74.37)
    assert manhattan.rent_psf_year == pytest.approx(64.6696, abs=1e-4)
    brooklyn = by_key[("county", "36047")]
    assert (brooklyn.property_type, brooklyn.rent_psf_year) == ("industrial_overall", 25.15)
    los_angeles = by_key[("cbsa", "31084")]
    assert los_angeles.reported_unit == "usd_psf_month"
    assert los_angeles.rent_psf_year == pytest.approx(15.96)
    assert by_key[("cbsa", "12420")].property_type == "industrial_flex"
    # The Kidder Mathews Peninsula row stays in rent_cbsa.csv, not here.
    assert ("cbsa", "41884") not in by_key
    kidder = read_rent_seed(bundled_seed_dir() / "rent_cbsa.csv")
    assert [(row.cbsa, row.rent_psf_year) for row in kidder] == [("41884", 25.68)]


def _csv(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _row(**changes: str) -> dict[str, str]:
    row = {
        "geography_level": "cbsa",
        "geography_id": "12420",
        "market": "Austin",
        "submarket": "Austin Totals",
        "property_type": "industrial_flex",
        "rent_psf_year": "18.0000",
        "reported_rent": "1.50",
        "reported_unit": "usd_psf_month",
        "reported_basis": "nnn",
        "source": "Cushman & Wakefield",
        "report": "MarketBeat Test Q3 2026",
        "quarter": "2026Q3",
        "as_of": "2026-09-30",
        "url": "https://example.com/report",
        "note": "Test row.",
    }
    row.update(changes)
    return row


@pytest.mark.parametrize(
    "rows",
    [
        [_row(rent_psf_year="1.50")],
        [_row(), _row()],
        [_row(geography_level="state")],
        [_row(geography_id="1242")],
        [_row(property_type="retail")],
        [_row(url="http://example.com")],
        [_row(note="")],
    ],
    ids=["unconverted", "duplicate", "level", "id", "type", "url", "note"],
)
def test_reader_rejects_bad_rows(tmp_path: Path, rows: list[dict[str, str]]) -> None:
    path = tmp_path / "rent_market.csv"
    path.write_text(_csv(rows), encoding="utf-8")
    with pytest.raises(RentSeedError):
        read_rent_market_seed(path)


def test_sync_loads_once_and_rewrites_a_stale_table(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "rent_market.csv").write_text(_csv([_row()]), encoding="utf-8")
    conn = get_connection(tmp_path)
    try:
        assert sync_rent_market(conn, seed_dir, fetched_at="2026-11-09T00:00:00Z") == 1
        first = list_rent_market(conn)
        assert [(row.geography_id, row.rent_psf_year) for row in first] == [("12420", 18.0)]
        assert first[0].fetched_at == "2026-11-09T00:00:00Z"
        source = get_source(conn, "broker_rent_market")
        assert source is not None and source.as_of == "2026-09-30"
        # Unchanged seed: no rewrite, so fetched_at keeps the first load.
        sync_rent_market(conn, seed_dir, fetched_at="2026-12-01T00:00:00Z")
        assert list_rent_market(conn) == first
        (seed_dir / "rent_market.csv").write_text(
            _csv([_row(rent_psf_year="24.0000", reported_rent="2.00")]), encoding="utf-8"
        )
        sync_rent_market(conn, seed_dir, fetched_at="2026-12-01T00:00:00Z")
        updated = list_rent_market(conn)
        assert [(row.rent_psf_year, row.fetched_at) for row in updated] == [
            (24.0, "2026-12-01T00:00:00Z")
        ]
    finally:
        conn.close()


def _resolver_db(tmp_path: Path) -> sqlite3.Connection:
    """Five ZIPs: a county broker row, a CBSA broker row, Kidder, and two with neither."""
    conn = get_connection(tmp_path)
    places = (
        ("10001", "36061", "NY", "New York County", "35614", 3361.0),
        ("11231", "36047", "NY", "Kings County", "35614", 2400.0),
        ("10601", "36119", "NY", "Westchester County", "35614", 1900.0),
        ("78701", "48453", "TX", "Travis County", "12420", 2759.0),
        ("94402", "06081", "CA", "San Mateo County", "41884", 3501.0),
        ("76801", "48049", "TX", "Brown County", "15220", 900.0),
    )
    replace_zip_geography(
        conn,
        tuple(
            ZipCountyRecord(zip_code, county, state, 1.0, name, "2026-11-09")
            for zip_code, county, state, name, _, _ in places
        ),
        tuple(ZipCbsaRecord(zip_code, cbsa, 1.0, "test") for zip_code, _, _, _, cbsa, _ in places),
        tuple(ZipZctaRecord(zip_code, zip_code, 1.0) for zip_code, *_ in places),
    )
    for zip_code, *_, rent in places:
        upsert_zcta_acs(
            conn,
            ZctaAcsRecord(
                zip_code, 2024, 1000.0, 80000.0, None, None, 500000.0, median_gross_rent=rent
            ),
        )
    replace_rent_cbsa(
        conn,
        (
            RentCbsaRecord(
                "41884", "industrial", 25.68, "2026-09-30", "Kidder Mathews Q3 2026.", "Kidder"
            ),
        ),
    )
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "rent_market.csv").write_text(
        _csv(
            [
                _row(),
                _row(geography_id="41884", rent_psf_year="99.0000", reported_rent="8.25"),
                _row(
                    geography_level="county",
                    geography_id="36061",
                    market="New York City",
                    submarket="Manhattan",
                    property_type="office_showroom_proxy",
                    rent_psf_year=f"{74.37 / 1.15:.4f}",
                    reported_rent="74.37",
                    reported_unit="usd_psf_year",
                    reported_basis="full_service_gross",
                ),
                _row(
                    geography_level="county",
                    geography_id="36047",
                    market="New York City",
                    submarket="Brooklyn",
                    property_type="industrial_overall",
                    rent_psf_year="25.1500",
                    reported_rent="25.15",
                    reported_unit="usd_psf_year",
                ),
                # A second TX metro and a third: the state median must still ignore them.
                _row(
                    geography_id="19124",
                    rent_psf_year="12.9800",
                    reported_rent="12.98",
                    reported_unit="usd_psf_year",
                ),
                _row(
                    geography_id="26420",
                    rent_psf_year="12.0200",
                    reported_rent="12.02",
                    reported_unit="usd_psf_year",
                ),
            ]
        ),
        encoding="utf-8",
    )
    sync_rent_market(conn, seed_dir, fetched_at="2026-11-09T00:00:00Z")
    return conn


def test_county_broker_rent_wins_and_is_not_acs_scaled(tmp_path: Path) -> None:
    conn = _resolver_db(tmp_path)
    try:
        manhattan = resolve_rent("10001", conn)
        brooklyn = resolve_rent("11231", conn)
    finally:
        conn.close()
    assert manhattan.tier == "broker_county"
    assert manhattan.property_type == "office_showroom_proxy"
    assert manhattan.confidence == "medium"
    assert manhattan.rent_psf_year == pytest.approx(64.6696, abs=1e-4)
    assert manhattan.rent_psf_month == pytest.approx(74.37 / 1.15 / 12)
    assert "full-service gross" in manhattan.citation
    assert "Not scaled by residential ACS rent" in manhattan.citation
    assert brooklyn.tier == "broker_county"
    assert brooklyn.confidence == "high"
    assert brooklyn.rent_psf_year == pytest.approx(25.15)


def test_cbsa_broker_rent_comes_before_acs_and_after_kidder(tmp_path: Path) -> None:
    conn = _resolver_db(tmp_path)
    try:
        austin = resolve_rent("78701", conn)
        san_mateo = resolve_rent("94402", conn)
        westchester = resolve_rent("10601", conn)
        rural_texas = resolve_rent("76801", conn)
    finally:
        conn.close()
    assert austin.tier == "broker_cbsa"
    assert austin.property_type == "industrial_flex"
    assert austin.rent_psf_year == pytest.approx(18.0)
    assert austin.as_of == "2026-09-30"
    assert "https://example.com/report" in austin.citation
    # The observed Kidder Mathews Peninsula rate keeps precedence in 41884.
    assert san_mateo.tier == "cbsa_raw"
    assert san_mateo.rent_psf_year == pytest.approx(25.68)
    # Same CBSA as Manhattan, different county, no broker row: ACS fallback.
    assert westchester.tier == "acs_gross_rent"
    assert westchester.rent_psf_year == pytest.approx(1900.0 * 12 / 1000)
    # Three TX metros in rent_market do not make a Texas state rent.
    assert rural_texas.tier == "acs_gross_rent"
    assert rural_texas.property_type == "residential_proxy"
