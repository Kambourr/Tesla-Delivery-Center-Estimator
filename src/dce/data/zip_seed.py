"""Load the bundled nationwide ZIP seed into SQLite.

The files under ``data/seed/`` are public-domain extracts plus cited broker
headlines (``rent_cbsa.csv`` and ``rent_market.csv``). Loading them does not
use the network. ``resolve_zip``
reads the crosswalk CSV directly so the geo package does not open SQLite.
``load_zip_seed`` copies the same files into the user database.
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from dce.config import bundled_seed_dir
from dce.data.ingest.census_acs import ZctaAcs, acs_as_of
from dce.data.ingest.zcta_gazetteer import ZctaCentroid
from dce.data.ingest.zip_geography import ZipCrosswalkRow
from dce.data.rent_defaults import read_rent_market_seed, read_rent_model, read_rent_seed
from dce.storage.repository import (
    OewsWageRecord,
    RentCbsaRecord,
    RentMarketRecord,
    RentModelRecord,
    SourceRecord,
    ZctaAcsRecord,
    ZctaCentroidRecord,
    ZevCountySalesRecord,
    ZevZipSalesRecord,
    ZipCbsaRecord,
    ZipCountyRecord,
    ZipZctaRecord,
    list_rent_market,
    replace_rent_cbsa,
    replace_rent_market,
    replace_zcta_acs_year,
    replace_zcta_centroids,
    replace_zev_sales,
    replace_zip_geography,
    upsert_oews_wages,
    upsert_rent_model,
    upsert_source,
)

CROSSWALK_CSV = "zip_crosswalk.csv"
CENTROID_CSV = "zcta_centroid_2024.csv"
ACS_CSV = "zcta_acs_2024.csv"
OEWS_CSV = "oews_metro_2025.csv"
RENT_CSV = "rent_cbsa.csv"
RENT_MODEL_JSON = "rent_model_coeffs.json"
RENT_MARKET_CSV = "rent_market.csv"
ZEV_ZIP_CSV = "zev_zip_sales.csv"
ZEV_COUNTY_CSV = "zev_county_sales.csv"
_CROSSWALK_FIELDS = (
    "zip",
    "zcta",
    "county_fips",
    "county_name",
    "cbsa",
    "cbsa_name",
    "state",
    "tot_ratio",
)
_CENTROID_FIELDS = ("zcta", "lat", "lon", "land_sqmi", "vintage", "as_of")
_ACS_FIELDS = (
    "zcta",
    "year",
    "population",
    "households",
    "median_hh_income",
    "median_gross_rent",
    "median_home_value",
    "vehicles_available",
    "mean_commute",
)
_OEWS_FIELDS = (
    "area_code",
    "area_name",
    "soc",
    "soc_title",
    "mean_annual",
    "median_annual",
    "as_of",
)


class ZipSeedError(ValueError):
    """A bundled ZIP seed file is missing or malformed."""


@dataclass(frozen=True)
class ZipSeedCounts:
    """How many rows ``load_zip_seed`` wrote."""

    crosswalk_rows: int
    centroids: int
    acs_rows: int
    oews_rows: int
    rent_rows: int
    zev_zip_rows: int
    zev_county_rows: int
    rent_market_rows: int = 0


def write_crosswalk_csv(path: Path, rows: Sequence[ZipCrosswalkRow]) -> None:
    """Write the crosswalk seed. Leading zeros are preserved."""
    _write_dicts(
        path,
        _CROSSWALK_FIELDS,
        [
            {
                "zip": row.zip_code,
                "zcta": row.zcta,
                "county_fips": row.county_fips,
                "county_name": row.county_name,
                "cbsa": row.cbsa,
                "cbsa_name": row.cbsa_name,
                "state": row.state,
                "tot_ratio": _ratio(row.tot_ratio),
            }
            for row in rows
        ],
    )


def read_crosswalk_csv(path: Path) -> tuple[ZipCrosswalkRow, ...]:
    """Read the crosswalk seed."""
    rows: list[ZipCrosswalkRow] = []
    for raw in _read_dicts(path, _CROSSWALK_FIELDS):
        rows.append(
            ZipCrosswalkRow(
                zip_code=_code(raw, "zip"),
                zcta=_code(raw, "zcta"),
                county_fips=_code(raw, "county_fips"),
                county_name=raw["county_name"].strip(),
                cbsa=raw["cbsa"].strip(),
                cbsa_name=raw["cbsa_name"].strip(),
                state=raw["state"].strip(),
                tot_ratio=float(raw["tot_ratio"]),
            )
        )
    if not rows:
        raise ZipSeedError(f"Crosswalk seed {path} has no rows.")
    return tuple(rows)


def write_centroid_csv(path: Path, rows: Sequence[ZctaCentroid]) -> None:
    """Write gazetteer internal points."""
    _write_dicts(
        path,
        _CENTROID_FIELDS,
        [
            {
                "zcta": row.zcta,
                "lat": repr(row.lat),
                "lon": repr(row.lon),
                "land_sqmi": "" if row.land_sqmi is None else repr(row.land_sqmi),
                "vintage": row.vintage,
                "as_of": row.as_of,
            }
            for row in rows
        ],
    )


def read_centroid_csv(path: Path) -> tuple[ZctaCentroid, ...]:
    """Read gazetteer internal points."""
    rows: list[ZctaCentroid] = []
    for raw in _read_dicts(path, _CENTROID_FIELDS):
        land = raw["land_sqmi"].strip()
        rows.append(
            ZctaCentroid(
                zcta=_code(raw, "zcta"),
                lat=float(raw["lat"]),
                lon=float(raw["lon"]),
                vintage=raw["vintage"].strip(),
                as_of=raw["as_of"].strip(),
                land_sqmi=None if land == "" else float(land),
            )
        )
    if not rows:
        raise ZipSeedError(f"Centroid seed {path} has no rows.")
    return tuple(rows)


def write_acs_csv(path: Path, rows: Sequence[ZctaAcs]) -> None:
    """Write per-ZCTA ACS measures. Blank cells are missing estimates."""
    _write_dicts(
        path,
        _ACS_FIELDS,
        [
            {
                "zcta": row.zcta,
                "year": str(row.year),
                "population": _num(row.population),
                "households": _num(row.households),
                "median_hh_income": _num(row.median_hh_income),
                "median_gross_rent": _num(row.median_gross_rent),
                "median_home_value": _num(row.median_home_value),
                "vehicles_available": _num(row.vehicles_available),
                "mean_commute": _num(row.mean_commute),
            }
            for row in rows
        ],
    )


def read_acs_csv(path: Path) -> tuple[ZctaAcs, ...]:
    """Read per-ZCTA ACS measures."""
    rows: list[ZctaAcs] = []
    for raw in _read_dicts(path, _ACS_FIELDS):
        rows.append(
            ZctaAcs(
                zcta=_code(raw, "zcta"),
                year=int(raw["year"]),
                population=_optional_num(raw["population"]),
                households=_optional_num(raw["households"]),
                median_hh_income=_optional_num(raw["median_hh_income"]),
                median_gross_rent=_optional_num(raw["median_gross_rent"]),
                median_home_value=_optional_num(raw["median_home_value"]),
                vehicles_available=_optional_num(raw["vehicles_available"]),
                mean_commute=_optional_num(raw["mean_commute"]),
            )
        )
    if not rows:
        raise ZipSeedError(f"ACS seed {path} has no rows.")
    return tuple(rows)


def write_oews_csv(path: Path, rows: Sequence[OewsWageRecord]) -> None:
    """Write metro wages."""
    _write_dicts(
        path,
        _OEWS_FIELDS,
        [
            {
                "area_code": row.area_code,
                "area_name": row.area_name,
                "soc": row.soc,
                "soc_title": row.soc_title,
                "mean_annual": _num(row.mean_annual),
                "median_annual": _num(row.median_annual),
                "as_of": row.as_of,
            }
            for row in rows
        ],
    )


def read_oews_csv(path: Path) -> tuple[OewsWageRecord, ...]:
    """Read metro wages."""
    rows: list[OewsWageRecord] = []
    for raw in _read_dicts(path, _OEWS_FIELDS):
        rows.append(
            OewsWageRecord(
                area_code=raw["area_code"].strip(),
                area_name=raw["area_name"].strip(),
                soc=raw["soc"].strip(),
                soc_title=raw["soc_title"].strip(),
                mean_annual=_optional_num(raw["mean_annual"]),
                median_annual=_optional_num(raw["median_annual"]),
                as_of=raw["as_of"].strip(),
            )
        )
    if not rows:
        raise ZipSeedError(f"OEWS seed {path} has no rows.")
    return tuple(rows)


def load_zip_seed(
    conn: sqlite3.Connection,
    seed_dir: Path | None = None,
    *,
    fetched_at: str,
) -> ZipSeedCounts:
    """Replace crosswalk, centroid, ACS, OEWS, and rent rows from the seed files."""
    directory = bundled_seed_dir() if seed_dir is None else seed_dir
    crosswalk = read_crosswalk_csv(directory / CROSSWALK_CSV)
    centroids = read_centroid_csv(directory / CENTROID_CSV)
    acs_rows = read_acs_csv(directory / ACS_CSV)
    wages = read_oews_csv(directory / OEWS_CSV)
    rents = read_rent_seed(directory / RENT_CSV)
    model = read_rent_model(directory / RENT_MODEL_JSON)
    counties, cbsas, zctas = _geography_records(crosswalk)
    replace_zip_geography(conn, counties, cbsas, zctas)
    replace_zcta_centroids(
        conn,
        [
            ZctaCentroidRecord(
                zcta=row.zcta,
                lat=row.lat,
                lon=row.lon,
                vintage=row.vintage,
                as_of=row.as_of,
                land_sqmi=row.land_sqmi,
            )
            for row in centroids
        ],
        vintage=centroids[0].vintage,
    )
    year = acs_rows[0].year
    replace_zcta_acs_year(
        conn,
        [
            ZctaAcsRecord(
                zcta=row.zcta,
                year=row.year,
                population=row.population,
                median_hh_income=row.median_hh_income,
                vehicles_available=row.vehicles_available,
                mean_commute=row.mean_commute,
                median_home_value=row.median_home_value,
                households=row.households,
                median_gross_rent=row.median_gross_rent,
            )
            for row in acs_rows
        ],
        year=year,
    )
    upsert_oews_wages(conn, wages)
    replace_rent_cbsa(
        conn,
        [
            RentCbsaRecord(
                cbsa=row.cbsa,
                property_type=row.property_type,
                rent_psf_year=row.rent_psf_year,
                as_of=row.as_of,
                citation=row.citation,
                broker=row.broker,
                fetched_at=fetched_at,
            )
            for row in rents
        ],
    )
    upsert_rent_model(
        conn,
        RentModelRecord(
            model_id=model.model_id,
            formula_json=model.formula_json,
            trained_on=model.trained_on,
            as_of=model.as_of,
        ),
    )
    market_rows = sync_rent_market(conn, directory, fetched_at=fetched_at)
    zev_zips, zev_counties = _load_zev(conn, directory, fetched_at=fetched_at)
    _registry(conn, fetched_at=fetched_at, acs_year=year)
    return ZipSeedCounts(
        crosswalk_rows=len(crosswalk),
        centroids=len(centroids),
        acs_rows=len(acs_rows),
        oews_rows=len(wages),
        rent_rows=len(rents),
        zev_zip_rows=len(zev_zips),
        zev_county_rows=len(zev_counties),
        rent_market_rows=market_rows,
    )


def sync_rent_market(
    conn: sqlite3.Connection,
    seed_dir: Path | None = None,
    *,
    fetched_at: str,
) -> int:
    """Make ``rent_market`` match the bundled ``rent_market.csv``. Returns the row count.

    A database seeded before this file existed (or from an older copy of it)
    is rewritten. A database that already matches is left alone, so repeated
    calls do not write. The bundled CSV is the only writer of this table.
    """
    directory = bundled_seed_dir() if seed_dir is None else seed_dir
    wanted = tuple(
        RentMarketRecord(
            geography_level=row.geography_level,
            geography_id=row.geography_id,
            market=row.market,
            submarket=row.submarket,
            property_type=row.property_type,
            rent_psf_year=row.rent_psf_year,
            reported_rent=row.reported_rent,
            reported_unit=row.reported_unit,
            reported_basis=row.reported_basis,
            source=row.source,
            report=row.report,
            quarter=row.quarter,
            as_of=row.as_of,
            url=row.url,
            note=row.note,
        )
        for row in read_rent_market_seed(directory / RENT_MARKET_CSV)
    )
    stored = tuple(replace(row, fetched_at=None) for row in list_rent_market(conn))
    if stored == wanted:
        return len(wanted)
    replace_rent_market(conn, [replace(row, fetched_at=fetched_at) for row in wanted])
    newest = max(row.as_of for row in wanted)
    upsert_source(
        conn,
        SourceRecord(
            source_id="broker_rent_market",
            url=wanted[0].url,
            as_of=newest,
            fetched_at=fetched_at,
            ttl_days=183,
            license_note=(
                "Headline asking rents transcribed from public broker market reports "
                "(Cushman & Wakefield MarketBeats). Facts and citations only; the reports "
                "are not stored."
            ),
            byte_count=None,
        ),
    )
    return len(wanted)


def _geography_records(
    rows: Sequence[ZipCrosswalkRow],
) -> tuple[tuple[ZipCountyRecord, ...], tuple[ZipCbsaRecord, ...], tuple[ZipZctaRecord, ...]]:
    counties = [
        ZipCountyRecord(
            zip_code=row.zip_code,
            county_fips=row.county_fips,
            state=row.state,
            tot_ratio=row.tot_ratio,
            county_name=row.county_name,
            as_of="2026-11-09",
        )
        for row in rows
    ]
    cbsa_totals: dict[tuple[str, str], list[float | str]] = {}
    for row in rows:
        if len(row.cbsa) != 5:
            continue
        key = (row.zip_code, row.cbsa)
        current = cbsa_totals.get(key)
        if current is None:
            cbsa_totals[key] = [row.tot_ratio, row.cbsa_name]
        else:
            current[0] = float(current[0]) + row.tot_ratio
    cbsas = [
        ZipCbsaRecord(
            zip_code=zip_code,
            cbsa=cbsa,
            tot_ratio=float(payload[0]),
            cbsa_name=str(payload[1]),
            as_of="2026-11-09",
        )
        for (zip_code, cbsa), payload in sorted(cbsa_totals.items())
    ]
    zcta_best: dict[tuple[str, str], float] = {}
    for row in rows:
        key = (row.zip_code, row.zcta)
        zcta_best[key] = max(zcta_best.get(key, 0.0), row.tot_ratio)
    zctas = [
        ZipZctaRecord(zip_code=zip_code, zcta=zcta, tot_ratio=ratio)
        for (zip_code, zcta), ratio in sorted(zcta_best.items())
    ]
    return tuple(counties), tuple(cbsas), tuple(zctas)


def _load_zev(
    conn: sqlite3.Connection, directory: Path, *, fetched_at: str
) -> tuple[tuple[ZevZipSalesRecord, ...], tuple[ZevCountySalesRecord, ...]]:
    zip_path = directory / ZEV_ZIP_CSV
    county_path = directory / ZEV_COUNTY_CSV
    if not zip_path.is_file() or not county_path.is_file():
        return (), ()
    zips = _read_zev_zips(zip_path)
    counties = _read_zev_counties(county_path)
    replace_zev_sales(conn, zips, counties)
    upsert_source(
        conn,
        SourceRecord(
            source_id="cec_zev_sales",
            url="https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data",
            as_of=zips[0].as_of if zips else fetched_at[:10],
            fetched_at=fetched_at,
            ttl_days=548,
            license_note=(
                "California Energy Commission New ZEV Sales. "
                "California open data. Outside California, ev_proxy is acs_national_fallback."
            ),
            byte_count=None,
        ),
        commit=False,
    )
    return zips, counties


def _read_zev_zips(path: Path) -> tuple[ZevZipSalesRecord, ...]:
    fields = (
        "zip",
        "state",
        "data_year",
        "quarter",
        "fuel_type",
        "vehicles",
        "as_of",
        "source",
    )
    return tuple(
        ZevZipSalesRecord(
            zip_code=_code(raw, "zip"),
            state=raw["state"].strip(),
            data_year=int(raw["data_year"]),
            quarter=int(raw["quarter"]),
            fuel_type=raw["fuel_type"].strip(),
            vehicles=int(raw["vehicles"]),
            as_of=raw["as_of"].strip(),
            source=raw["source"].strip(),
        )
        for raw in _read_dicts(path, fields)
    )


def _read_zev_counties(path: Path) -> tuple[ZevCountySalesRecord, ...]:
    fields = (
        "county",
        "state",
        "data_year",
        "quarter",
        "fuel_type",
        "make",
        "vehicles",
        "as_of",
        "source",
    )
    return tuple(
        ZevCountySalesRecord(
            county=raw["county"].strip(),
            state=raw["state"].strip(),
            data_year=int(raw["data_year"]),
            quarter=int(raw["quarter"]),
            fuel_type=raw["fuel_type"].strip(),
            make=raw["make"].strip(),
            vehicles=int(raw["vehicles"]),
            as_of=raw["as_of"].strip(),
            source=raw["source"].strip(),
        )
        for raw in _read_dicts(path, fields)
    )


def _registry(conn: sqlite3.Connection, *, fetched_at: str, acs_year: int) -> None:
    records = (
        SourceRecord(
            source_id="census_zcta_gazetteer",
            url="https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip",
            as_of="2024-01-01",
            fetched_at=fetched_at,
            ttl_days=548,
            license_note=(
                "U.S. Census Bureau Gazetteer Files, ZCTA internal points. "
                "Public domain (US government work)."
            ),
            byte_count=None,
        ),
        SourceRecord(
            source_id="census_zip_crosswalk",
            url="https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt",
            as_of="2020-01-01",
            fetched_at=fetched_at,
            ttl_days=548,
            license_note=(
                "U.S. Census Bureau 2020 ZCTA-to-county relationship file and "
                "July 2023 CBSA delineation. Public domain (US government work). "
                "ZIP Codes that are not ZCTAs come from the HRSA 2025 ZIP-to-ZCTA crosswalk."
            ),
            byte_count=None,
        ),
        SourceRecord(
            source_id="census_acs",
            url=f"https://www2.census.gov/programs-surveys/acs/summary_file/{acs_year}/table-based-SF/data/5YRData/",
            as_of=acs_as_of(acs_year),
            fetched_at=fetched_at,
            ttl_days=548,
            license_note=(
                "U.S. Census Bureau American Community Survey 5-year estimates. "
                "Public domain (US government work)."
            ),
            byte_count=None,
        ),
        SourceRecord(
            source_id="bls_oews",
            url="https://api.bls.gov/publicAPI/v2/timeseries/data/",
            as_of="2025-05-01",
            fetched_at=fetched_at,
            ttl_days=548,
            license_note=(
                "U.S. Bureau of Labor Statistics Occupational Employment and Wage Statistics. "
                "Public domain (US government work)."
            ),
            byte_count=None,
        ),
        SourceRecord(
            source_id="hrsa_zip_zcta",
            url="https://data.hrsa.gov/DataDownload/GeoCareNavigator/ZIPCodetoZCTACrosswalk2025UDS.xlsx",
            as_of="2025-01-01",
            fetched_at=fetched_at,
            ttl_days=548,
            license_note=(
                "HRSA GeoCare Navigator ZIP Code to ZCTA Crosswalk, 2025. "
                "U.S. Department of Health and Human Services. US government work."
            ),
            byte_count=None,
        ),
    )
    for record in records:
        upsert_source(conn, record, commit=False)
    conn.commit()


def _write_dicts(path: Path, fields: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_dicts(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ZipSeedError(f"Could not read {path}.") from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None or tuple(reader.fieldnames) != tuple(fields):
        raise ZipSeedError(f"{path.name} columns must be {', '.join(fields)}.")
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({key: (raw.get(key) or "") for key in fields})
    return rows


def _code(row: dict[str, str], key: str) -> str:
    text = row[key].strip()
    if len(text) != 5 or not text.isdigit():
        raise ZipSeedError(f"{key} must be 5 digits, got {text!r}.")
    return text


def _ratio(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _num(value: float | None) -> str:
    if value is None:
        return ""
    return repr(value)


def _optional_num(value: str) -> float | None:
    text = value.strip()
    if text == "":
        return None
    return float(text)
