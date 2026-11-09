"""Per-ZIP local inputs for the precompute and the map UI.

``load_zip_local`` reads SQLite only. Call :func:`dce.data.zip_seed.load_zip_seed`
once so the bundled extracts are in the database. The click on a ZCTA polygon
passes that ZCTA code, which is the ZIP for every polygon Census draws.

Outside California, vehicle counts are not invented. ``ev.ev_proxy`` is
``acs_national_fallback`` and ``ev.source`` is ``fallback``. The caller can
pass the ZIP's households, income, and an EV share into
``dce.data.ingest.zev_sales.allocate_state_tesla_volume`` when it has a state
Tesla total. California uses stored CEC ZIP sales and the county Tesla share
when those rows have been loaded.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from dce.data.ingest.bls_oews import OEWS_NATIONAL_AREA, oews_area_for_cbsa
from dce.data.rent_resolver import RentResolution, RentResolutionError, resolve_rent
from dce.model.types import GeoContext
from dce.storage.repository import (
    OewsWageRecord,
    ZevZipSalesRecord,
    get_latest_ev_zip,
    get_latest_zcta_acs,
    get_zcta_centroid,
    list_oews_wages,
    list_zev_county_year,
    list_zev_zip_year,
    list_zip_cbsas,
    list_zip_counties,
    list_zip_zctas,
)


class ZipLocalError(ValueError):
    """The ZIP is not in the local crosswalk or is not 5 digits."""

    def __init__(self, zip_code: str, message: str) -> None:
        self.zip_code = zip_code
        super().__init__(message)


@dataclass(frozen=True)
class ZipEvLocal:
    """Vehicle facts for one ZIP.

    ``source`` is ``cec``, ``dmv``, ``fallback``, or ``missing``.
    ``ev_proxy`` is ``acs_national_fallback`` outside California and ``None``
    when a California file applies or the state is unknown.
    ``tesla_bev_sales`` is ZIP battery-electric sales times the county Tesla
    share for the newest stored year. It is ``None`` when either input is absent.
    """

    zip_code: str
    state: str
    source: str
    ev_proxy: str | None
    as_of: str | None
    bev: int | None
    phev: int | None
    fcev: int | None
    total_ldv: int | None
    tesla_bev_sales: float | None
    county_tesla_share: float | None
    citation: str


@dataclass(frozen=True)
class ZipLocalData:
    """Everything the map and the precompute need for one ZIP."""

    geo: GeoContext
    county_name: str
    cbsa_name: str
    oews_area: str
    lat: float | None
    lon: float | None
    land_sqmi: float | None
    acs_year: int | None
    population: float | None
    households: float | None
    median_hh_income: float | None
    median_gross_rent: float | None
    median_home_value: float | None
    vehicles_available: float | None
    mean_commute: float | None
    rent: RentResolution | None
    rent_error: str | None
    wages: tuple[OewsWageRecord, ...]
    wage_basis: str
    ev: ZipEvLocal


def load_zip_local(
    zip_code: str, conn: sqlite3.Connection, *, persist_rent: bool = True
) -> ZipLocalData:
    """Return local geography, ACS, rent, wages, and EV facts for one ZIP.

    ``persist_rent`` writes ``rent_resolved_cache``. Batch callers can skip
    the write. The resolved rent is the same either way.
    """
    code = _zip(zip_code)
    zctas = list_zip_zctas(conn, code)
    counties = list_zip_counties(conn, code)
    if not zctas or not counties:
        raise ZipLocalError(code, f"ZIP {code} is not in the local crosswalk.")
    zcta = zctas[0].zcta
    county = counties[0]
    cbsa_rows = list_zip_cbsas(conn, code)
    cbsa = cbsa_rows[0].cbsa if cbsa_rows else ""
    cbsa_name = cbsa_rows[0].cbsa_name if cbsa_rows else ""
    geo = GeoContext(
        zip_code=code,
        zcta=zcta,
        county_fips=county.county_fips,
        cbsa=cbsa,
        state=county.state,
    )
    centroid = get_zcta_centroid(conn, zcta, "2024")
    acs = get_latest_zcta_acs(conn, zcta)
    rent, rent_error = _rent(code, conn, persist_rent=persist_rent)
    oews_area = oews_area_for_cbsa(cbsa) if len(cbsa) == 5 else ""
    wages = list_oews_wages(conn, oews_area) if oews_area else ()
    wage_basis = "cbsa" if wages else "national"
    if not wages:
        wages = list_oews_wages(conn, OEWS_NATIONAL_AREA)
        oews_area = OEWS_NATIONAL_AREA if wages else oews_area
    return ZipLocalData(
        geo=geo,
        county_name=county.county_name,
        cbsa_name=cbsa_name,
        oews_area=oews_area,
        lat=None if centroid is None else centroid.lat,
        lon=None if centroid is None else centroid.lon,
        land_sqmi=None if centroid is None else centroid.land_sqmi,
        acs_year=None if acs is None else acs.year,
        population=None if acs is None else acs.population,
        households=None if acs is None else acs.households,
        median_hh_income=None if acs is None else acs.median_hh_income,
        median_gross_rent=None if acs is None else acs.median_gross_rent,
        median_home_value=None if acs is None else acs.median_home_value,
        vehicles_available=None if acs is None else acs.vehicles_available,
        mean_commute=None if acs is None else acs.mean_commute,
        rent=rent,
        rent_error=rent_error,
        wages=wages,
        wage_basis=wage_basis if wages else "missing",
        ev=_ev(code, county.state, county.county_name, conn),
    )


def _rent(
    zip_code: str, conn: sqlite3.Connection, *, persist_rent: bool
) -> tuple[RentResolution | None, str | None]:
    try:
        return resolve_rent(zip_code, conn, write_cache=persist_rent), None
    except RentResolutionError as exc:
        return None, str(exc)


def _ev(zip_code: str, state: str, county_name: str, conn: sqlite3.Connection) -> ZipEvLocal:
    if state != "CA":
        return ZipEvLocal(
            zip_code=zip_code,
            state=state,
            source="fallback",
            ev_proxy="acs_national_fallback",
            as_of=None,
            bev=None,
            phev=None,
            fcev=None,
            total_ldv=None,
            tesla_bev_sales=None,
            county_tesla_share=None,
            citation=(
                "No California Energy Commission ZEV file covers this state. "
                "Allocate a state Tesla total with households, income, and EV share "
                "(dce.data.ingest.zev_sales.allocate_state_tesla_volume). "
                "ev_proxy is acs_national_fallback."
            ),
        )
    counts = get_latest_ev_zip(conn, zip_code)
    sales = list_zev_zip_year(conn, zip_code)
    share, share_as_of = _county_share(conn, county_name)
    tesla = _tesla_sales(sales, share)
    if sales:
        return ZipEvLocal(
            zip_code=zip_code,
            state=state,
            source="cec",
            ev_proxy=None,
            as_of=sales[0].as_of,
            bev=_fuel(sales, "electric"),
            phev=_fuel(sales, "phev"),
            fcev=_fuel(sales, "hydrogen"),
            total_ldv=None if counts is None else counts.total_ldv,
            tesla_bev_sales=tesla,
            county_tesla_share=share,
            citation=(
                "California Energy Commission New ZEV Sales. ZIP fuel counts, "
                "and Tesla's share of battery-electric sales in the county."
            ),
        )
    if counts is not None:
        return ZipEvLocal(
            zip_code=zip_code,
            state=state,
            source=counts.source,
            ev_proxy=None,
            as_of=counts.as_of,
            bev=counts.bev,
            phev=counts.phev,
            fcev=counts.fcev,
            total_ldv=counts.total_ldv,
            tesla_bev_sales=None,
            county_tesla_share=share,
            citation="California DMV fuel-type counts by ZIP, light-duty rows, via data.ca.gov.",
        )
    return ZipEvLocal(
        zip_code=zip_code,
        state=state,
        source="missing",
        ev_proxy=None,
        as_of=share_as_of,
        bev=None,
        phev=None,
        fcev=None,
        total_ldv=None,
        tesla_bev_sales=None,
        county_tesla_share=share,
        citation=(
            "California ZIP, but no CEC or DMV rows are stored for it. "
            "Load the CEC workbook or the DMV fuel-type file."
        ),
    )


def _county_share(conn: sqlite3.Connection, county_name: str) -> tuple[float | None, str | None]:
    short = _county_key(county_name)
    rows = list_zev_county_year(conn, short)
    if not rows:
        rows = list_zev_county_year(conn, county_name)
    electric = [row for row in rows if row.fuel_type.casefold() == "electric"]
    total = sum(row.vehicles for row in electric)
    if total <= 0:
        return None, None
    tesla = sum(row.vehicles for row in electric if row.make.casefold() == "tesla")
    return tesla / total, electric[0].as_of


def _tesla_sales(
    sales: tuple[ZevZipSalesRecord, ...],
    share: float | None,
) -> float | None:
    if share is None:
        return None
    electric = _fuel(sales, "electric")
    if electric is None:
        return None
    return electric * share


def _fuel(sales: tuple[ZevZipSalesRecord, ...], fuel: str) -> int | None:
    matched = [row.vehicles for row in sales if row.fuel_type.casefold() == fuel]
    if not matched:
        return None
    return sum(matched)


def _county_key(name: str) -> str:
    text = name.strip()
    for suffix in (
        " County",
        " Parish",
        " Borough",
        " Census Area",
        " Municipality",
        " city",
    ):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _zip(zip_code: str) -> str:
    text = zip_code.strip()
    if len(text) != 5 or not text.isdigit():
        raise ZipLocalError(text, f"ZIP must be 5 digits, got {zip_code.strip()!r}.")
    return text
