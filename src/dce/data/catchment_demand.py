"""ZIP-level Tesla demand for the catchment. No network.

California reads the committed Bay Area extract (2025 CEC ZIP battery-electric
sales within 55 miles of 94402). Each ZIP is anchored to its county's CEC
Tesla total:

    D_z = BEV_z * (CEC Tesla_county / sum of BEV_z in that county)

A county with no CEC Tesla row in the extract keeps the 2025 9-county Tesla
share of Electric sales, 49,704 / 94,131. That is the documented California
fallback. County membership is the hand list in :func:`county_of` (a ZCTA
that straddles a county line is counted once, in its main county).

Every ZIP is then multiplied by the handover factor. Registrations are not
handovers. The assumptions file holds low 1.00 / base 1.10 / high 1.30.
Base 1.10 is what ``estimate`` passes. 1.10 and 1.30 are assumptions: no
public source counts used-car handovers. See
``docs/research/demand_calibration.md``.

Outside California, :func:`non_california_zip_demand` splits a state Tesla
total with the households form in :mod:`dce.data.ingest.zev_sales`. When the
caller has EV registrations but no Tesla make split, the total is
registrations times the national Tesla share of US EV sales (Cox/KBB 2025,
46.2%). Household counts come from ACS ``B11001_001E``. A ZIP missing
households, income, EV stock, or light-duty total is left out.

The competing sites are every ``delivery`` row in the US snapshot, not the
ten Bay Area research rows. The hub and the possible-handover rows stay out:
they are not on the Find Us delivery list.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from dce.config import demo_data_dir
from dce.data.ingest.census_acs import ZctaAcs
from dce.data.ingest.delivery_centers import load_us_delivery_centers
from dce.data.ingest.zev_sales import ZipDemandProfile, allocate_state_tesla_volume
from dce.geo.catchment import CenterSite, ZipDemand
from dce.model.types import GeoContext

# docs/research/tesla_delivery_ops_research.md §4.2, CEC county sheet, 2025.
# Tesla Electric 49,704 / Electric 94,131 in the 9-county Bay Area.
# Used only where a county has no CEC Tesla total in the extract.
BAY_AREA_TESLA_BEV_SHARE = 49704 / 94131

# Cox Automotive / Kelley Blue Book, Q4 2025 EV Sales Report, read 2026-11-09.
# Tesla US sales 589,160 were 46.2% of US EV sales.
# https://www.coxautoinc.com/wp-content/uploads/2026/01/Q4-2025-Kelley-Blue-Book-EV-Sales-Report.pdf
# Non-California fallback when the caller has EV registrations and no make split.
NATIONAL_TESLA_EV_SHARE = 0.462

# CEC New ZEV Sales, make = Tesla, calendar 2025, by county.
# https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data
# (workbook data to 2026-09-30, read 2026-11-08; quoted in the research note).
CEC_TESLA_2025: dict[str, int] = {
    "San Mateo": 5296,
    "San Francisco": 3456,
    "Santa Clara": 20214,
    "Alameda": 11061,
    "Contra Costa": 5535,
    "Marin": 1259,
}

# Main county of each Bay Area extract ZCTA. A straddling ZCTA is listed once.
# The sets match docs/research/data/demand_calibration.py.
_SAN_MATEO = {
    "94002", "94005", "94010", "94014", "94015", "94018", "94019", "94020",
    "94025", "94027", "94028", "94030", "94037", "94038", "94044", "94060",
    "94061", "94062", "94063", "94065", "94066", "94070", "94074", "94080",
    "94128", "94401", "94402", "94403", "94404",
}  # fmt: skip
_SANTA_CLARA_EXTRA = {
    "94022", "94024", "94040", "94041", "94043", "94085", "94086", "94087",
    "94089", "94301", "94303", "94304", "94305", "94306",
}  # fmt: skip
_SANTA_CRUZ = {
    "95003", "95005", "95006", "95010", "95017", "95018", "95019", "95041",
    "95060", "95062", "95064", "95065", "95066", "95073", "95076",
}  # fmt: skip
_SAN_JOAQUIN = {"95304", "95376", "95377", "95391"}
_CONTRA_COSTA_94 = {
    "94505", "94506", "94507", "94509", "94511", "94513", "94514", "94516",
    "94517", "94518", "94519", "94520", "94521", "94523", "94525", "94526",
    "94528", "94530", "94531", "94547", "94548", "94549", "94553", "94556",
    "94561", "94563", "94564", "94565", "94569", "94572", "94582", "94583",
    "94595", "94596", "94597", "94598", "94707", "94708",
}  # fmt: skip
_SOLANO = {"94510", "94533", "94534", "94535", "94571", "94585", "94589", "94590", "94591", "94592"}
_NAPA = {"94503", "94558", "94559"}
_SONOMA = {"94952", "94954", "95476"}


class CatchmentDemandError(ValueError):
    """Catchment demand for this ZIP is not in the local public inputs."""


def county_of(zip_code: str) -> str:
    """Return the main county name for a Bay Area extract ZCTA.

    ``"Other"`` means the hand list has no row. Those ZIPs keep the 9-county
    Tesla share instead of a county total.
    """
    if zip_code in _SAN_MATEO:
        return "San Mateo"
    if zip_code.startswith("941"):
        return "San Francisco"
    if zip_code in _SANTA_CRUZ:
        return "Santa Cruz"
    if zip_code in _SAN_JOAQUIN:
        return "San Joaquin"
    if zip_code in _SANTA_CLARA_EXTRA or zip_code.startswith(("950", "951")):
        return "Santa Clara"
    if zip_code in _SOLANO:
        return "Solano"
    if zip_code in _NAPA:
        return "Napa"
    if zip_code in _SONOMA:
        return "Sonoma"
    if zip_code in _CONTRA_COSTA_94 or zip_code.startswith("948"):
        return "Contra Costa"
    if zip_code.startswith(("945", "946", "947")):
        return "Alameda"
    if zip_code.startswith("949"):
        return "Marin"
    return "Other"


def bay_area_demand_path() -> Path:
    """Return the committed 2025 Bay Area BEV extract."""
    return demo_data_dir() / "san_mateo" / "catchment_bev_2025.csv"


def delivery_center_sites() -> tuple[CenterSite, ...]:
    """Return every Find Us delivery center in the US snapshot.

    ``location_type`` ``delivery`` only. The North San Jose hub and the
    possible-handover rows are not on the Find Us delivery list, so they
    stay out of the allocation. The same rule kept the hub out of the Bay
    Area research set. Stockton, Seaside, and Sacramento fall inside the
    60-mile cap for 94402, which is why an uncalibrated gravity total moves
    from 5,522.8 on the nine research centers to 5,483.3 on this list.
    """
    return tuple(
        CenterSite(row.center_id, row.name, row.lat, row.lon)
        for row in load_us_delivery_centers()
        if row.location_type == "delivery"
    )


def bay_area_zip_demand(
    path: Path | None = None,
    *,
    handover_factor: float = 1.0,
    county_anchor: bool = True,
) -> tuple[ZipDemand, ...]:
    """Read the Bay Area BEV extract and turn it into Tesla handovers.

    ``county_anchor`` replaces the single 9-county share with each county's
    CEC Tesla total. Counties missing from :data:`CEC_TESLA_2025` keep
    :data:`BAY_AREA_TESLA_BEV_SHARE`. ``handover_factor`` then scales every
    ZIP. ``1.0`` with ``county_anchor=False`` is the pre-calibration series
    (BEV times 49,704 / 94,131). ``estimate`` passes the assumptions base,
    1.10, with the anchor on.
    """
    factor = _positive("handover_factor", handover_factor)
    source = bay_area_demand_path() if path is None else path
    raw = _read_bev_rows(source)
    bev_by_county: dict[str, float] = {}
    located: list[tuple[str, float, float, int, str]] = []
    for zip_code, lat, lon, bev in raw:
        county = county_of(zip_code)
        bev_by_county[county] = bev_by_county.get(county, 0.0) + bev
        located.append((zip_code, lat, lon, bev, county))
    rows: list[ZipDemand] = []
    for zip_code, lat, lon, bev, county in located:
        share = _county_share(county, bev_by_county) if county_anchor else BAY_AREA_TESLA_BEV_SHARE
        rows.append(ZipDemand(zip_code, lat, lon, bev * share * factor))
    return tuple(sorted(rows, key=lambda row: row.zip_code))


def non_california_zip_demand(
    state_tesla_volume: float,
    acs_rows: Sequence[ZctaAcs],
    ev_stock_by_zip: Mapping[str, float | None],
    total_ldv_by_zip: Mapping[str, float | None],
    centroids: Mapping[str, tuple[float, float]],
) -> tuple[ZipDemand, ...]:
    """Allocate a state Tesla total using ACS households.

    ``ev_stock_by_zip`` and ``total_ldv_by_zip`` are vehicles. A missing
    household count, income, EV stock, light-duty total, or centroid drops
    that ZIP. The returned deliveries sum to ``state_tesla_volume`` when
    every weighted ZIP has a centroid.
    """
    profiles: list[ZipDemandProfile] = []
    for row in acs_rows:
        profiles.append(
            ZipDemandProfile(
                zip_code=row.zcta,
                households=row.households,
                median_hh_income=row.median_hh_income,
                ev_stock=ev_stock_by_zip.get(row.zcta),
                total_ldv=total_ldv_by_zip.get(row.zcta),
            )
        )
    allocated = allocate_state_tesla_volume(state_tesla_volume, profiles)
    demand: list[ZipDemand] = []
    for zip_code in sorted(allocated):
        point = centroids.get(zip_code)
        if point is None:
            continue
        lat, lon = point
        demand.append(ZipDemand(zip_code, lat, lon, allocated[zip_code]))
    return tuple(demand)


def build_catchment_demand(
    geo: GeoContext,
    *,
    state_tesla_volume: float | None = None,
    state_ev_registrations: float | None = None,
    tesla_ev_share: float | None = None,
    handover_factor: float = 1.0,
    acs_rows: Sequence[ZctaAcs] = (),
    ev_stock_by_zip: Mapping[str, float | None] | None = None,
    total_ldv_by_zip: Mapping[str, float | None] | None = None,
    centroids: Mapping[str, tuple[float, float]] | None = None,
) -> tuple[ZipDemand, ...]:
    """Return ZIP demand for ``geo``, including the candidate ZIP.

    California reads the committed Bay Area extract, anchors it to CEC
    county Tesla totals, and applies ``handover_factor``. Any other state
    uses :func:`non_california_zip_demand`. Pass ``state_tesla_volume``, or
    pass ``state_ev_registrations`` and the national Tesla share of EV sales
    is applied (``tesla_ev_share``, default :data:`NATIONAL_TESLA_EV_SHARE`).
    The handover factor scales that allocation too. The bundled demo has
    the California extract only, so a non-California ZIP fails clearly when
    those inputs are absent.
    """
    factor = _positive("handover_factor", handover_factor)
    if geo.state == "CA":
        demand = bay_area_zip_demand(handover_factor=factor)
    else:
        volume = _state_tesla_volume(
            geo.zip_code,
            state_tesla_volume=state_tesla_volume,
            state_ev_registrations=state_ev_registrations,
            tesla_ev_share=tesla_ev_share,
        )
        if ev_stock_by_zip is None or total_ldv_by_zip is None:
            raise CatchmentDemandError(
                f"ZIP {geo.zip_code} is outside California. The demand fallback needs "
                "a state Tesla total (or state EV registrations), ACS households, "
                "income, and EV counts."
            )
        if centroids is None:
            raise CatchmentDemandError(
                f"ZIP {geo.zip_code} is outside California and has no ZCTA centroids."
            )
        demand = _scale(
            non_california_zip_demand(
                volume,
                acs_rows,
                ev_stock_by_zip,
                total_ldv_by_zip,
                centroids,
            ),
            factor,
        )
    usable = {
        row.zip_code
        for row in demand
        if row.lat is not None and row.lon is not None and row.deliveries_per_year is not None
    }
    if geo.zip_code not in usable and geo.zcta not in usable:
        raise CatchmentDemandError(
            f"ZIP {geo.zip_code} has no catchment demand (a centroid and deliveries "
            "are both required)."
        )
    return demand


def _county_share(county: str, bev_by_county: Mapping[str, float]) -> float:
    tesla = CEC_TESLA_2025.get(county)
    bev = bev_by_county.get(county, 0.0)
    if tesla is None or bev <= 0.0:
        return BAY_AREA_TESLA_BEV_SHARE
    return tesla / bev


def _state_tesla_volume(
    zip_code: str,
    *,
    state_tesla_volume: float | None,
    state_ev_registrations: float | None,
    tesla_ev_share: float | None,
) -> float:
    if state_tesla_volume is not None and state_ev_registrations is not None:
        raise CatchmentDemandError("Pass a state Tesla total or state EV registrations, not both.")
    if state_tesla_volume is not None:
        return _non_negative("state_tesla_volume", state_tesla_volume)
    if state_ev_registrations is None:
        raise CatchmentDemandError(
            f"ZIP {zip_code} is outside California. The demand fallback needs "
            "a state Tesla total or state EV registrations, plus ACS households, "
            "income, and EV counts."
        )
    registrations = _non_negative("state_ev_registrations", state_ev_registrations)
    share = NATIONAL_TESLA_EV_SHARE if tesla_ev_share is None else tesla_ev_share
    return registrations * _share(share)


def _read_bev_rows(source: Path) -> list[tuple[str, float, float, int]]:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatchmentDemandError(f"Could not read catchment demand: {source}.") from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None or not {"zip", "lat", "lon", "bev_2025"} <= set(reader.fieldnames):
        raise CatchmentDemandError("Catchment demand CSV is missing zip, lat, lon, or bev_2025.")
    rows: list[tuple[str, float, float, int]] = []
    for record in reader:
        try:
            bev = int(record["bev_2025"])
            if bev < 0:
                raise ValueError
            rows.append((record["zip"], float(record["lat"]), float(record["lon"]), bev))
        except (TypeError, ValueError) as exc:
            raise CatchmentDemandError(
                f"Catchment demand row {record.get('zip')!r} is not usable."
            ) from exc
    if not rows:
        raise CatchmentDemandError("Catchment demand CSV has no ZIP rows.")
    return rows


def _scale(rows: Sequence[ZipDemand], factor: float) -> tuple[ZipDemand, ...]:
    if factor == 1.0:
        return tuple(rows)
    scaled: list[ZipDemand] = []
    for row in rows:
        deliveries = row.deliveries_per_year
        scaled.append(
            ZipDemand(
                row.zip_code,
                row.lat,
                row.lon,
                None if deliveries is None else deliveries * factor,
            )
        )
    return tuple(scaled)


def _positive(name: str, value: float) -> float:
    number = _finite(name, value)
    if number <= 0.0:
        raise CatchmentDemandError(f"{name} must be > 0, got {value!r}.")
    return number


def _non_negative(name: str, value: float) -> float:
    number = _finite(name, value)
    if number < 0.0:
        raise CatchmentDemandError(f"{name} must be >= 0, got {value!r}.")
    return number


def _share(value: float) -> float:
    number = _positive("tesla_ev_share", value)
    if number > 1.0:
        raise CatchmentDemandError(f"tesla_ev_share must be <= 1, got {value!r}.")
    return number


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CatchmentDemandError(f"{name} must be a finite number, got {value!r}.")
    return float(value)
