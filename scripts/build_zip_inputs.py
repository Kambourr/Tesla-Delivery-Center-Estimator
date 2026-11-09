"""Rebuild the nationwide ZIP seed from public files.

Writes ``data/seed/zip_crosswalk.csv``, ``zcta_centroid_2024.csv``,
``zcta_acs_2024.csv``, ``oews_metro_2025.csv``, ``rent_cbsa.csv``,
``rent_model_coeffs.json``, and, when the CEC workbook downloads,
``zev_zip_sales.csv`` plus ``zev_county_sales.csv``. Also writes
``data/seed/coverage.json``.

Cached downloads live under ``--cache`` (default ``data/cache/zip_inputs``,
gitignored). A rebuild from that cache does not re-download Census or HRSA.
``--fetch-bls`` and ``--fetch-zev`` are the only network steps in that case.

Curator allowlist, separate from the runtime allowlist in
``dce.data.ingest.http`` (which is not widened):

* ``www2.census.gov`` gazetteer, ZCTA-county relationship, CBSA list 1,
  ACS 5-year table-based summary files
* ``data.hrsa.gov`` 2025 ZIP-to-ZCTA workbook (not a runtime host)
* ``api.bls.gov`` through ``dce.data.ingest.bls_oews``
* ``www.energy.ca.gov`` through ``dce.data.ingest.zev_sales``

HTTPS only. Redirects are refused. Accessed 2026-11-09.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dce.data.ingest.bls_oews import (
    OEWS_DELIVERY_SOCS,
    OEWS_NATIONAL_AREA,
    OEWS_NATIONAL_AREA_NAME,
    OEWS_SOC_AUTO_TECH,
    OEWS_SOC_TITLE_AUTO_TECH,
    OewsError,
    OewsWage,
    fetch_oews_area_wages,
)
from dce.data.ingest.census_acs import (
    GROSS_RENT_VARIABLE,
    HOME_VALUE_VARIABLE,
    HOUSEHOLDS_VARIABLE,
    INCOME_VARIABLE,
    POPULATION_VARIABLE,
    VEHICLES_VARIABLE,
    zcta_acs_from_summary_files,
)
from dce.data.ingest.xlsx_table import read_xlsx_rows
from dce.data.ingest.zcta_gazetteer import parse_gazetteer_zip
from dce.data.ingest.zev_sales import ZevSalesError, fetch_zev_sales
from dce.data.ingest.zip_geography import (
    CountyCbsa,
    ZipCrosswalkRow,
    assemble_zip_crosswalk,
    parse_cbsa_delineation,
    parse_hrsa_zip_zcta,
    parse_zcta_county_relationship,
)
from dce.data.zip_seed import (
    write_acs_csv,
    write_centroid_csv,
    write_crosswalk_csv,
    write_oews_csv,
)
from dce.storage.repository import OewsWageRecord

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"
ACS_YEAR = 2024
OEWS_YEAR = 2025
_ACS_FILES = {
    POPULATION_VARIABLE: "b01003",
    HOUSEHOLDS_VARIABLE: "b11001",
    INCOME_VARIABLE: "b19013",
    GROSS_RENT_VARIABLE: "b25064",
    HOME_VALUE_VARIABLE: "b25077",
    VEHICLES_VARIABLE: "b25046",
}
_RENT_CITATION = (
    "Kidder Mathews Peninsula Industrial Market Report Q3 2026, "
    "asking rent $2.14 per square foot per month ($25.68 per square foot per year). "
    "https://kidder.com/market-reports/peninsula-industrial-market-report/"
)
_HOSTS = ("www2.census.gov", "data.hrsa.gov")
_URLS = {
    "gazetteer": (
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
        "2024_Gazetteer/2024_Gaz_zcta_national.zip"
    ),
    "relationship": (
        "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
        "tab20_zcta520_county20_natl.txt"
    ),
    "delineation": (
        "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
        "reference-files/2023/delineation-files/list1_2023.xlsx"
    ),
    "hrsa": (
        "https://data.hrsa.gov/DataDownload/GeoCareNavigator/ZIPCodetoZCTACrosswalk2025UDS.xlsx"
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "cache" / "zip_inputs")
    parser.add_argument("--fetch-bls", action="store_true")
    parser.add_argument("--fetch-zev", action="store_true")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args(argv)
    cache = args.cache
    cache.mkdir(parents=True, exist_ok=True)
    if args.download:
        _download_missing(cache)
    relationship = _read(cache, "zcta_county.txt", "tab20_zcta520_county20_natl.txt")
    parts = parse_zcta_county_relationship(relationship.read_text(encoding="utf-8"))
    counties = parse_cbsa_delineation(read_xlsx_rows(_read_bytes(cache, "list1_2023.xlsx")))
    by_county = {row.county_fips: row for row in counties}
    hrsa = parse_hrsa_zip_zcta(read_xlsx_rows(_read_bytes(cache, "hrsa_zip_zcta_2025.xlsx")))
    crosswalk = _collapse(assemble_zip_crosswalk(parts, by_county, hrsa))
    centroids = parse_gazetteer_zip(_read_bytes(cache, "gazetteer.zip"), year=2024)
    tables = {variable: _acs_text(cache, stem) for variable, stem in _ACS_FILES.items()}
    acs_rows = zcta_acs_from_summary_files(ACS_YEAR, tables)
    wages = _wages(counties, fetch=args.fetch_bls, cache=cache)
    _write_rent()
    zev_counts = _zev(cache, fetch=args.fetch_zev)
    write_crosswalk_csv(SEED / "zip_crosswalk.csv", crosswalk)
    write_centroid_csv(SEED / "zcta_centroid_2024.csv", centroids)
    write_acs_csv(SEED / "zcta_acs_2024.csv", acs_rows)
    write_oews_csv(SEED / "oews_metro_2025.csv", wages)
    coverage = _coverage(crosswalk, centroids, acs_rows, wages, zev_counts, counties)
    (SEED / "coverage.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(coverage, indent=2, sort_keys=True))
    return 0


def _collapse(rows: tuple[ZipCrosswalkRow, ...]) -> tuple[ZipCrosswalkRow, ...]:
    """One row per ZIP and county. The larger land share wins a duplicate."""
    kept: dict[tuple[str, str], ZipCrosswalkRow] = {}
    for row in rows:
        key = (row.zip_code, row.county_fips)
        current = kept.get(key)
        if current is None or row.tot_ratio > current.tot_ratio:
            kept[key] = row
    ordered = sorted(kept.values(), key=lambda row: (row.zip_code, -row.tot_ratio, row.county_fips))
    return tuple(ordered)


def _wages(
    counties: tuple[CountyCbsa, ...], *, fetch: bool, cache: Path
) -> tuple[OewsWageRecord, ...]:
    cached = cache / "oews_metro_2025.csv"
    if not fetch and cached.is_file():
        from dce.data.zip_seed import read_oews_csv

        return read_oews_csv(cached)
    if not fetch:
        raise SystemExit("Pass --fetch-bls or place oews_metro_2025.csv in the cache.")
    metros: dict[str, str] = {}
    for county in counties:
        if county.metropolitan:
            metros[county.parent_cbsa] = county.parent_name
    found: dict[tuple[str, str], OewsWage] = {}
    _merge(found, _safe_fetch((), OEWS_DELIVERY_SOCS, national=True))
    bay = metros.get("41860", "San Francisco-Oakland-Fremont, CA")
    _merge(
        found,
        _safe_fetch((("41860", bay),), OEWS_DELIVERY_SOCS, national=False),
    )
    auto = ((OEWS_SOC_AUTO_TECH, OEWS_SOC_TITLE_AUTO_TECH),)
    areas = sorted(metros.items())
    for start in range(0, len(areas), 25):
        batch = areas[start : start + 25]
        got = _safe_fetch(tuple(batch), auto, national=False, datatype_mean_only=True)
        if got is None:
            break
        _merge(found, got)
        time.sleep(0.4)
    for start in range(0, len(areas), 25):
        batch = areas[start : start + 25]
        got = _safe_fetch(tuple(batch), auto, national=False, datatype_median_only=True)
        if got is None:
            break
        _merge(found, got)
        time.sleep(0.4)
    if not found:
        raise SystemExit("BLS returned no OEWS rows.")
    records = tuple(
        OewsWageRecord(
            area_code=row.area_code,
            area_name=row.area_name,
            soc=row.soc,
            soc_title=row.soc_title,
            mean_annual=row.mean_annual,
            median_annual=row.median_annual,
            as_of=row.as_of,
        )
        for row in sorted(found.values(), key=lambda row: (row.area_code, row.soc))
    )
    write_oews_csv(cached, records)
    return records


def _safe_fetch(
    areas: tuple[tuple[str, str], ...],
    socs: tuple[tuple[str, str], ...],
    *,
    national: bool,
    datatype_mean_only: bool = False,
    datatype_median_only: bool = False,
) -> tuple[OewsWage, ...] | None:
    datatypes = ("04", "13")
    if datatype_mean_only:
        datatypes = ("04",)
    if datatype_median_only:
        datatypes = ("13",)
    try:
        return fetch_oews_area_wages(
            areas, socs, datatypes=datatypes, national=national, end_year=OEWS_YEAR
        )
    except OewsError as exc:
        print(f"BLS stopped: {exc}", file=sys.stderr)
        return None


def _merge(found: dict[tuple[str, str], OewsWage], rows: tuple[OewsWage, ...] | None) -> None:
    if rows is None:
        return
    for row in rows:
        key = (row.area_code, row.soc)
        current = found.get(key)
        if current is None:
            found[key] = row
            continue
        found[key] = OewsWage(
            area_code=row.area_code,
            area_name=row.area_name or current.area_name,
            soc=row.soc,
            soc_title=row.soc_title or current.soc_title,
            mean_annual=row.mean_annual if row.mean_annual is not None else current.mean_annual,
            median_annual=(
                row.median_annual if row.median_annual is not None else current.median_annual
            ),
            as_of=max(row.as_of, current.as_of),
        )


def _zev(cache: Path, *, fetch: bool) -> dict[str, int]:
    zip_out = SEED / "zev_zip_sales.csv"
    county_out = SEED / "zev_county_sales.csv"
    if not fetch and zip_out.is_file() and county_out.is_file():
        return {
            "zev_zip_rows": _count_csv(zip_out),
            "zev_county_rows": _count_csv(county_out),
        }
    if not fetch:
        return {"zev_zip_rows": 0, "zev_county_rows": 0}
    try:
        batch = fetch_zev_sales()
    except ZevSalesError as exc:
        print(f"CEC workbook skipped: {exc}", file=sys.stderr)
        return {"zev_zip_rows": 0, "zev_county_rows": 0}
    (cache / "zev_source_url.txt").write_text(batch.source_url + "\n", encoding="utf-8")
    newest = max(row.data_year for row in batch.zip_sales)
    zip_rows = [row for row in batch.zip_sales if row.data_year == newest]
    county_rows = [row for row in batch.county_sales if row.data_year == newest]
    _write_dicts(
        zip_out,
        ("zip", "state", "data_year", "quarter", "fuel_type", "vehicles", "as_of", "source"),
        [
            {
                "zip": row.zip_code,
                "state": row.state,
                "data_year": str(row.data_year),
                "quarter": str(row.quarter),
                "fuel_type": row.fuel_type,
                "vehicles": str(row.vehicles),
                "as_of": row.as_of,
                "source": row.source,
            }
            for row in zip_rows
        ],
    )
    _write_dicts(
        county_out,
        (
            "county",
            "state",
            "data_year",
            "quarter",
            "fuel_type",
            "make",
            "vehicles",
            "as_of",
            "source",
        ),
        [
            {
                "county": row.county,
                "state": row.state,
                "data_year": str(row.data_year),
                "quarter": str(row.quarter),
                "fuel_type": row.fuel_type,
                "make": row.make,
                "vehicles": str(row.vehicles),
                "as_of": row.as_of,
                "source": row.source,
            }
            for row in county_rows
        ],
    )
    return {
        "zev_zip_rows": len(zip_rows),
        "zev_county_rows": len(county_rows),
        "zev_year": newest,
        "zev_source_url": batch.source_url,
    }


def _write_rent() -> None:
    _write_dicts(
        SEED / "rent_cbsa.csv",
        ("cbsa", "property_type", "rent_psf_year", "as_of", "citation", "broker"),
        [
            {
                "cbsa": "41884",
                "property_type": "industrial",
                "rent_psf_year": "25.68",
                "as_of": "2026-09-30",
                "citation": _RENT_CITATION,
                "broker": "Kidder Mathews",
            }
        ],
    )
    model = {
        "model_id": "acs_rent_v1",
        "trained_on": (
            "Not fit to the GSA Lease Inventory. Shipped exponents use the ACS "
            "median gross rent ratio only. The model owner replaces b_income, "
            "b_density, and b_home_value after that calibration."
        ),
        "as_of": "2026-11-09",
        "b_acs_rent": 1,
        "b_income": 0,
        "b_density": 0,
        "b_home_value": 0,
        "clamp_low": 0.5,
        "clamp_high": 2.0,
        "unit_sqft": 1000,
        "commercial_residential_ratio": 1,
    }
    (SEED / "rent_model_coeffs.json").write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _coverage(
    crosswalk: tuple[ZipCrosswalkRow, ...],
    centroids: tuple[object, ...],
    acs_rows: tuple[object, ...],
    wages: tuple[OewsWageRecord, ...],
    zev_counts: dict[str, object],
    counties: tuple[CountyCbsa, ...],
) -> dict[str, object]:
    zctas = {row.zcta for row in crosswalk if row.zip_code == row.zcta}
    with_cbsa = {row.zcta for row in crosswalk if row.zip_code == row.zcta and len(row.cbsa) == 5}
    acs_zctas = {str(row.zcta) for row in acs_rows}

    def filled(name: str) -> int:
        return sum(1 for row in acs_rows if getattr(row, name) is not None)

    wage_areas = {row.area_code for row in wages if row.area_code != OEWS_NATIONAL_AREA}
    auto_areas = {
        row.area_code
        for row in wages
        if row.soc == OEWS_SOC_AUTO_TECH and row.area_code != OEWS_NATIONAL_AREA
    }
    metro_codes = {row.parent_cbsa for row in counties if row.metropolitan}
    missing = sorted(metro_codes - auto_areas)
    return {
        "accessed": "2026-11-09",
        "zip_rows": len({row.zip_code for row in crosswalk}),
        "crosswalk_rows": len(crosswalk),
        "zctas": len(zctas),
        "zctas_with_cbsa": len(with_cbsa),
        "centroids": len(centroids),
        "acs_zctas": len(acs_zctas),
        "acs_population": filled("population"),
        "acs_households": filled("households"),
        "acs_median_hh_income": filled("median_hh_income"),
        "acs_median_gross_rent": filled("median_gross_rent"),
        "acs_median_home_value": filled("median_home_value"),
        "acs_vehicles": filled("vehicles_available"),
        "oews_rows": len(wages),
        "oews_metro_areas": len(wage_areas),
        "oews_metro_areas_auto_tech": len(auto_areas),
        "oews_missing_cbsas": missing,
        "oews_national_area": OEWS_NATIONAL_AREA_NAME,
        "oews_note": (
            "May 2025. Metropolitan parent CBSAs with an annual SOC 49-3023 series "
            "are listed in oews_metro_areas_auto_tech. oews_missing_cbsas had no "
            "annual series (Guayama, PR is 25020 when that is the only gap). "
            "Micropolitan areas use national area 00000. Delivery-mix SOCs are "
            "stored for the nation and for CBSA 41860."
        ),
        **zev_counts,
    }


def _acs_text(cache: Path, stem: str) -> str:
    candidates = (
        cache / "acs" / f"{stem}.dat",
        cache / f"{stem}.dat",
        cache / "acs" / f"acsdt5y{ACS_YEAR}-{stem}.dat",
        cache / f"acsdt5y{ACS_YEAR}-{stem}.dat",
    )
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise SystemExit(f"ACS file {stem} is not in {cache}.")


def _read(cache: Path, *names: str) -> Path:
    for name in names:
        path = cache / name
        if path.is_file():
            return path
    raise SystemExit(f"Missing {' or '.join(names)} in {cache}.")


def _read_bytes(cache: Path, name: str) -> bytes:
    return _read(cache, name).read_bytes()


def _download_missing(cache: Path) -> None:
    targets = {
        "gazetteer": cache / "gazetteer.zip",
        "relationship": cache / "zcta_county.txt",
        "delineation": cache / "list1_2023.xlsx",
        "hrsa": cache / "hrsa_zip_zcta_2025.xlsx",
    }
    for key, path in targets.items():
        if path.is_file():
            continue
        _download(_URLS[key], path)


def _download(url: str, path: Path) -> None:
    hostname = urllib.parse.urlparse(url).hostname or ""
    if hostname not in _HOSTS or not url.startswith("https://"):
        raise SystemExit(f"Refusing {url}.")
    request = urllib.request.Request(url, headers={"User-Agent": "delivery-center-estimator"})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=180) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Download failed for {url}: {exc}") from exc
    path.write_bytes(payload)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirect refused to {newurl}",
            headers,  # type: ignore[arg-type]
            None,
        )


def _write_dicts(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _count_csv(path: Path) -> int:
    with path.open(encoding="utf-8") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


if __name__ == "__main__":
    raise SystemExit(main())
