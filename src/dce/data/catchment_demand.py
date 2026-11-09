"""ZIP-level Tesla demand for the catchment. No network.

California uses the committed Bay Area extract: 2025 CEC ZIP battery-electric
sales within 55 miles of 94402, times the 9-county Tesla share of Electric
sales (49,704 / 94,131). Centroids in that file are Census 2024 Gazetteer
internal points.

Outside California, :func:`non_california_zip_demand` splits a state Tesla
total with the households form in :mod:`dce.data.ingest.zev_sales`. Household
counts come from ACS ``B11001_001E``. A ZIP missing households, income, EV
stock, or light-duty total is left out.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path

from dce.config import demo_data_dir
from dce.data.ingest.census_acs import ZctaAcs
from dce.data.ingest.delivery_centers import load_delivery_centers
from dce.data.ingest.zev_sales import ZipDemandProfile, allocate_state_tesla_volume
from dce.geo.catchment import CenterSite, ZipDemand
from dce.model.types import GeoContext

# docs/research/tesla_delivery_ops_research.md §4.2, 2025 CEC county sheet.
BAY_AREA_TESLA_BEV_SHARE = 49704 / 94131


class CatchmentDemandError(ValueError):
    """Catchment demand for this ZIP is not in the local public inputs."""


def bay_area_demand_path() -> Path:
    """Return the committed 2025 Bay Area BEV extract."""
    return demo_data_dir() / "san_mateo" / "catchment_bev_2025.csv"


def delivery_center_sites() -> tuple[CenterSite, ...]:
    """Return the Find Us delivery centers from the committed snapshot.

    The North San Jose row is a hub, not a Find Us delivery center on the
    snapshot date. The research nearest-center total uses the nine delivery
    centers. Adding the hub does not change that nearest total and does
    change gravity, so the estimate leaves the hub out of the allocation.
    """
    return tuple(
        CenterSite(row.center_id, row.name, row.lat, row.lon)
        for row in load_delivery_centers()
        if row.location_type == "delivery"
    )


def bay_area_zip_demand(path: Path | None = None) -> tuple[ZipDemand, ...]:
    """Read the Bay Area BEV extract and apply the 9-county Tesla share."""
    source = bay_area_demand_path() if path is None else path
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatchmentDemandError(f"Could not read catchment demand: {source}.") from exc
    rows: list[ZipDemand] = []
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None or not {"zip", "lat", "lon", "bev_2025"} <= set(reader.fieldnames):
        raise CatchmentDemandError("Catchment demand CSV is missing zip, lat, lon, or bev_2025.")
    for record in reader:
        try:
            rows.append(
                ZipDemand(
                    record["zip"],
                    float(record["lat"]),
                    float(record["lon"]),
                    int(record["bev_2025"]) * BAY_AREA_TESLA_BEV_SHARE,
                )
            )
        except (TypeError, ValueError) as exc:
            raise CatchmentDemandError(
                f"Catchment demand row {record.get('zip')!r} is not usable."
            ) from exc
    if not rows:
        raise CatchmentDemandError("Catchment demand CSV has no ZIP rows.")
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
    acs_rows: Sequence[ZctaAcs] = (),
    ev_stock_by_zip: Mapping[str, float | None] | None = None,
    total_ldv_by_zip: Mapping[str, float | None] | None = None,
    centroids: Mapping[str, tuple[float, float]] | None = None,
) -> tuple[ZipDemand, ...]:
    """Return ZIP demand for ``geo``, including the candidate ZIP.

    California reads the committed Bay Area extract. Any other state uses
    :func:`non_california_zip_demand` and therefore needs a state Tesla total
    plus ACS households. The bundled demo has that extract only for the Bay
    Area, so a non-California ZIP fails clearly when those inputs are absent.
    """
    if geo.state == "CA":
        demand = bay_area_zip_demand()
    else:
        if state_tesla_volume is None or ev_stock_by_zip is None or total_ldv_by_zip is None:
            raise CatchmentDemandError(
                f"ZIP {geo.zip_code} is outside California. The demand fallback needs "
                "a state Tesla total, ACS households, income, and EV counts."
            )
        if centroids is None:
            raise CatchmentDemandError(
                f"ZIP {geo.zip_code} is outside California and has no ZCTA centroids."
            )
        demand = non_california_zip_demand(
            state_tesla_volume,
            acs_rows,
            ev_stock_by_zip,
            total_ldv_by_zip,
            centroids,
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
