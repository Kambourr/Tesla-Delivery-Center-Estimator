"""Nationwide ZIP origin demand for the gravity catchment.

California uses the CEC rows ``load_zip_seed`` stored. The shipped file is
calendar 2026 through quarter 3 (``as_of`` 2026-09-30). Those counts are
scaled by ``4 / quarters_in_file`` so the DCF sees an annual rate. The
research note's San Mateo run-rate (4,145 × 4/3 ≈ 5,527) is that same
scaling. It is a flat annualization: quarter 4 is not inferred from the
seasonality table.

A California ZIP is ``BEV_z × (Tesla_county / BEV_county) × annualization
× handover``. A county with no Tesla row keeps the 2025 9-county share
49,704 / 94,131. A ZIP with no battery-electric row originates nothing.

Outside California the seed has no Tesla make split and no EV
registrations, so this module does not invent a state total. It allocates
the documented national residual:

    Cox/KBB Tesla US sales 2025, 589,160
    minus CEC California Tesla sales 2025, 169,650

across ZCTAs by households and the income elasticity in
``dce.data.ingest.zev_sales`` (0.3, reference $80,000). The EV-share term
is left at 1 because EV stock is not in the national file. A suppressed
income uses the $80,000 reference. Only a ZIP that is its own ZCTA receives
that weight, so a PO box is not a second copy of the same households.
The handover factor then scales the allocation, the same way it scales
California.

Both series are public. Neither is Tesla internal data.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from dce.data.catchment_demand import BAY_AREA_TESLA_BEV_SHARE
from dce.data.ingest.zev_sales import INCOME_ELASTICITY, INCOME_REFERENCE
from dce.storage.repository import (
    ZctaAcsRecord,
    list_zcta_acs_year,
    list_zcta_centroids,
    list_zev_county_sales,
    list_zev_zip_sales,
    list_zip_counties_all,
    list_zip_zctas_all,
)

# Cox Automotive / Kelley Blue Book, Q4 2025 EV Sales Report, read 2026-11-09.
# Tesla US sales 589,160. docs/research/demand_calibration.md §1.1.
US_TESLA_SALES_2025 = 589_160.0

# CEC New ZEV Sales, Tesla battery-electric, calendar 2025, read 2026-11-08.
# docs/research/demand_calibration.md §1.1. The ZIP seed itself is 2026 Q1–Q3.
CA_TESLA_SALES_2025 = 169_650.0

NON_CA_TESLA_SALES_2025 = US_TESLA_SALES_2025 - CA_TESLA_SALES_2025

_QUARTERS_IN_YEAR = 4


@dataclass(frozen=True)
class ZipPlace:
    """Dominant geography and centroid for one crosswalk ZIP."""

    zip_code: str
    zcta: str
    county_fips: str
    county_name: str
    state: str
    lat: float | None
    lon: float | None


@dataclass(frozen=True)
class NationalDemand:
    """Origin deliveries and the place each resolvable ZIP sits on."""

    places: dict[str, ZipPlace]
    deliveries: dict[str, float]
    handover_factor: float
    annualization: float
    quarters: tuple[int, ...]
    cec_as_of: str | None
    non_ca_tesla_before_handover: float

    def zip_codes(self) -> tuple[str, ...]:
        """Return every crosswalk ZIP, sorted."""
        return tuple(sorted(self.places))


def build_national_demand(conn: sqlite3.Connection, *, handover_factor: float) -> NationalDemand:
    """Build origin deliveries for every ZIP the crosswalk can place."""
    factor = _positive(handover_factor)
    places = _places(conn)
    acs = {row.zcta: row for row in list_zcta_acs_year(conn, 2024)}
    annualization, quarters, as_of, ca_raw = _california(conn, places)
    allocated = _non_california(places, acs, factor)
    deliveries: dict[str, float] = {}
    for zip_code, place in places.items():
        if place.lat is None or place.lon is None:
            continue
        if place.state == "CA":
            origin = ca_raw.get(zip_code, 0.0) * annualization * factor
        else:
            origin = allocated.get(zip_code, 0.0)
        if origin > 0.0:
            deliveries[zip_code] = origin
    return NationalDemand(
        places=places,
        deliveries=deliveries,
        handover_factor=factor,
        annualization=annualization,
        quarters=quarters,
        cec_as_of=as_of,
        non_ca_tesla_before_handover=NON_CA_TESLA_SALES_2025,
    )


def _places(conn: sqlite3.Connection) -> dict[str, ZipPlace]:
    counties: dict[str, tuple[tuple[float, str], str, str, str]] = {}
    for county_row in list_zip_counties_all(conn):
        county_rank = (-county_row.tot_ratio, county_row.county_fips)
        held = counties.get(county_row.zip_code)
        if held is None or county_rank < held[0]:
            counties[county_row.zip_code] = (
                county_rank,
                county_row.county_fips,
                county_row.state,
                county_row.county_name,
            )
    zctas: dict[str, tuple[tuple[float, str], str]] = {}
    for zcta_link in list_zip_zctas_all(conn):
        zcta_rank = (-zcta_link.tot_ratio, zcta_link.zcta)
        held_zcta = zctas.get(zcta_link.zip_code)
        if held_zcta is None or zcta_rank < held_zcta[0]:
            zctas[zcta_link.zip_code] = (zcta_rank, zcta_link.zcta)
    centroids = {row.zcta: row for row in list_zcta_centroids(conn, "2024")}
    places: dict[str, ZipPlace] = {}
    for zip_code, county in counties.items():
        zcta_row = zctas.get(zip_code)
        if zcta_row is None:
            continue
        zcta = zcta_row[1]
        point = centroids.get(zcta)
        places[zip_code] = ZipPlace(
            zip_code=zip_code,
            zcta=zcta,
            county_fips=county[1],
            county_name=county[3],
            state=county[2],
            lat=None if point is None else point.lat,
            lon=None if point is None else point.lon,
        )
    return places


def _california(
    conn: sqlite3.Connection, places: dict[str, ZipPlace]
) -> tuple[float, tuple[int, ...], str | None, dict[str, float]]:
    """Return annualization, quarters, as_of, and unscaled Tesla counts by ZIP."""
    zip_rows = list_zev_zip_sales(conn)
    county_rows = list_zev_county_sales(conn)
    if not zip_rows or not county_rows:
        return 1.0, (), None, {}
    year = max(sale.data_year for sale in zip_rows)
    quarters = tuple(sorted({sale.quarter for sale in zip_rows if sale.data_year == year}))
    annualization = _QUARTERS_IN_YEAR / len(quarters) if quarters else 1.0
    as_of = next((sale.as_of for sale in zip_rows if sale.data_year == year), None)
    electric_zip: dict[str, float] = {}
    for sale in zip_rows:
        if sale.data_year != year or sale.fuel_type.casefold() != "electric":
            continue
        electric_zip[sale.zip_code] = electric_zip.get(sale.zip_code, 0.0) + sale.vehicles
    bev_county: dict[str, float] = {}
    tesla_county: dict[str, float] = {}
    for county_sale in county_rows:
        if county_sale.data_year != year or county_sale.fuel_type.casefold() != "electric":
            continue
        key = county_sale.county.casefold()
        bev_county[key] = bev_county.get(key, 0.0) + county_sale.vehicles
        if county_sale.make.casefold() == "tesla":
            tesla_county[key] = tesla_county.get(key, 0.0) + county_sale.vehicles
    shares = {
        key: (BAY_AREA_TESLA_BEV_SHARE if bev <= 0.0 else tesla_county.get(key, 0.0) / bev)
        for key, bev in bev_county.items()
    }
    raw: dict[str, float] = {}
    for zip_code, electric in electric_zip.items():
        place = places.get(zip_code)
        county_key = "" if place is None else _county_key(place.county_name).casefold()
        raw[zip_code] = electric * shares.get(county_key, BAY_AREA_TESLA_BEV_SHARE)
    return annualization, quarters, as_of, raw


def _non_california(
    places: dict[str, ZipPlace],
    acs: dict[str, ZctaAcsRecord],
    handover_factor: float,
) -> dict[str, float]:
    weights: dict[str, float] = {}
    for zip_code, place in places.items():
        if place.state == "CA" or zip_code != place.zcta:
            continue
        row = acs.get(place.zcta)
        if row is None:
            continue
        weight = _weight(row.households, row.median_hh_income)
        if weight is None or weight <= 0.0:
            continue
        weights[zip_code] = weight
    scale = math.fsum(weights.values())
    if scale <= 0.0:
        return {}
    volume = NON_CA_TESLA_SALES_2025 * handover_factor
    return {zip_code: volume * weight / scale for zip_code, weight in weights.items()}


def _weight(households: float | None, income: float | None) -> float | None:
    if households is None or households < 0.0:
        return None
    used_income = INCOME_REFERENCE
    if income is not None and income > 0.0:
        used_income = income
    if households == 0.0:
        return 0.0
    return households * (used_income / INCOME_REFERENCE) ** INCOME_ELASTICITY


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


def _positive(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"handover_factor must be a finite number, got {value!r}.")
    if value <= 0.0:
        raise ValueError(f"handover_factor must be > 0, got {value}.")
    return float(value)
