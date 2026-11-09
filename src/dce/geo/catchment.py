"""Allocate a candidate ZIP's deliveries across competing centers.

Contract
--------
``catchment_features(geo, centers, demand, beta=2)`` replaces the M0
``catchment_features(geo, radius_miles)`` stub.

A delivery center serves the ZCTAs that choose it, not every ZIP inside a
fixed radius. Distance is the straight-line miles between points times
``1.25`` (a drive-distance proxy). Pairs whose proxy is above 60 miles are
out of range: beyond that, assume a farther center or Carrier Direct.

* Base case: Huff gravity with equal attractiveness and ``beta`` (default 2).
  The candidate's share of ZIP ``z`` is ``d_cz ** -beta / sum_k d_kz ** -beta``
  over in-range sites ``k``.
* Low case: nearest in-range site (Voronoi). Ties break by ``center_id``.

The candidate sits at the demand row for ``geo.zip_code`` (else ``geo.zcta``).
``centers`` are the existing sites and do not include the candidate.
``radius_miles`` is used only when ``centers`` is empty: ZIPs within that
straight-line radius are assigned entirely to the candidate. When it is
omitted, an empty center list still uses the 60-mile drive cap.

The return value reports, for both cases, the ZIPs with a positive
allocation, the total deliveries per year, and the volume taken from each
existing center (its share before the candidate minus its share after).

A ZIP whose coordinates or deliveries are missing is skipped. The candidate
ZIP itself must have both. This module does not read files, SQL, or the
network.

San Mateo 94402 on the committed Bay Area fixture (BEV times the 9-county
share, nine research centers) is about 5,523 gravity deliveries a year,
not the research text's about 5,720. Nearest-center is 4,370, which matches
the research, and the §4.4 radius table matches too. ``estimate`` does not
use that series: it passes county-anchored demand, the base handover
factor, and the US delivery list.
The 60-mile drive cap, the Gazetteer centroids, and rounding the Tesla
share to 0.528 do not explain the 200 deliveries. Opening the cap moves
the total slightly farther from 5,720. The gap is the fractional Huff
share of ZIPs that nearest-center assigns entirely to another site. The
research script is not in the repo, so this module keeps the ADR-0004
rule (equal attractiveness, beta 2, straight-line times 1.25, 60-mile
cap, all nine delivery centers) and the reproducible total is 5,523.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from dce.model.types import GeoContext

DRIVE_CIRCUITY = 1.25
MAX_DRIVE_MILES = 60.0
EARTH_RADIUS_MILES = 3958.7613
_CANDIDATE_ID = "candidate"
_DISTANCE_TIE_MILES = 1e-9


class CatchmentDataError(ValueError):
    """A catchment input is missing or not usable."""


@dataclass(frozen=True)
class CenterSite:
    """An existing supply point. Coordinates are decimal degrees."""

    center_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class ZipDemand:
    """One ZCTA's Tesla deliveries and centroid.

    ``None`` coordinates or deliveries mean the ZIP has no data and is left
    out of the allocation. The candidate ZIP cannot be missing.
    """

    zip_code: str
    lat: float | None
    lon: float | None
    deliveries_per_year: float | None


@dataclass(frozen=True)
class ZipAllocation:
    """Deliveries the candidate handles in one ZIP."""

    zip_code: str
    deliveries_per_year: float
    share: float
    straight_line_miles: float
    drive_miles: float


@dataclass(frozen=True)
class TakenFromCenter:
    """Deliveries the candidate takes from one existing center."""

    center_id: str
    name: str
    deliveries_per_year: float


@dataclass(frozen=True)
class CatchmentCase:
    """One allocation: gravity (base) or nearest center (low)."""

    method: Literal["gravity", "nearest"]
    beta: float | None
    zips: tuple[ZipAllocation, ...]
    total_deliveries_per_year: float
    taken_from: tuple[TakenFromCenter, ...]


@dataclass(frozen=True)
class CatchmentFeatures:
    """Gravity at ``beta`` and the nearest-center case for one candidate ZIP."""

    zip_code: str
    beta: float
    gravity: CatchmentCase
    nearest: CatchmentCase


@dataclass(frozen=True)
class _Site:
    center_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class _ZipPoint:
    zip_code: str
    lat: float
    lon: float
    deliveries: float


def straight_line_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle miles between two WGS84 points."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_MILES * 2 * math.asin(min(1.0, math.sqrt(haversine)))


def drive_distance_miles(straight_miles: float) -> float:
    """Return the uncapped drive proxy, straight-line miles times 1.25."""
    return straight_miles * DRIVE_CIRCUITY


def catchment_features(
    geo: GeoContext,
    centers: Sequence[CenterSite],
    demand: Sequence[ZipDemand],
    beta: float = 2.0,
    *,
    radius_miles: float | None = None,
) -> CatchmentFeatures:
    """Allocate ``demand`` between ``geo`` and the existing ``centers``.

    ``beta`` is the gravity distance exponent. The nearest-center case does
    not use it. See the module docstring for the 60-mile cap and the
    empty-center fallback.
    """
    exponent = _require_beta(beta)
    points = _usable_demand(demand)
    candidate = _candidate_point(geo, demand, points)
    sites = _existing_sites(centers)
    drive_cap, straight_cap = _caps(sites, radius_miles)

    gravity = _case(
        method="gravity",
        beta=exponent,
        candidate=candidate,
        sites=sites,
        points=points,
        drive_cap=drive_cap,
        straight_cap=straight_cap,
    )
    nearest = _case(
        method="nearest",
        beta=None,
        candidate=candidate,
        sites=sites,
        points=points,
        drive_cap=drive_cap,
        straight_cap=straight_cap,
    )
    return CatchmentFeatures(
        zip_code=candidate.zip_code,
        beta=exponent,
        gravity=gravity,
        nearest=nearest,
    )


def _case(
    *,
    method: Literal["gravity", "nearest"],
    beta: float | None,
    candidate: _ZipPoint,
    sites: tuple[_Site, ...],
    points: Mapping[str, _ZipPoint],
    drive_cap: float | None,
    straight_cap: float | None,
) -> CatchmentCase:
    before = _shares(
        points, sites, method=method, beta=beta, drive_cap=drive_cap, straight_cap=straight_cap
    )
    after_sites = sites + (_Site(_CANDIDATE_ID, "candidate", candidate.lat, candidate.lon),)
    after = _shares(
        points,
        after_sites,
        method=method,
        beta=beta,
        drive_cap=drive_cap,
        straight_cap=straight_cap,
    )
    allocations: list[ZipAllocation] = []
    taken: dict[str, float] = {site.center_id: 0.0 for site in sites}
    names = {site.center_id: site.name for site in sites}
    for zip_code in sorted(points):
        point = points[zip_code]
        share = after.get(zip_code, {}).get(_CANDIDATE_ID, 0.0)
        handled = point.deliveries * share
        if handled > 0.0:
            straight = straight_line_miles(candidate.lat, candidate.lon, point.lat, point.lon)
            allocations.append(
                ZipAllocation(
                    zip_code=zip_code,
                    deliveries_per_year=handled,
                    share=share,
                    straight_line_miles=straight,
                    drive_miles=drive_distance_miles(straight),
                )
            )
        prior = before.get(zip_code, {})
        later = after.get(zip_code, {})
        for center_id in taken:
            delta = point.deliveries * (prior.get(center_id, 0.0) - later.get(center_id, 0.0))
            if delta > 0.0:
                taken[center_id] += delta
    taken_rows = tuple(
        TakenFromCenter(center_id, names[center_id], deliveries)
        for center_id, deliveries in sorted(taken.items(), key=lambda item: (-item[1], item[0]))
        if deliveries > 0.0
    )
    total = sum(row.deliveries_per_year for row in allocations)
    return CatchmentCase(
        method=method,
        beta=beta,
        zips=tuple(allocations),
        total_deliveries_per_year=total,
        taken_from=taken_rows,
    )


def _shares(
    points: Mapping[str, _ZipPoint],
    sites: Sequence[_Site],
    *,
    method: Literal["gravity", "nearest"],
    beta: float | None,
    drive_cap: float | None,
    straight_cap: float | None,
) -> dict[str, dict[str, float]]:
    shares: dict[str, dict[str, float]] = {}
    for zip_code, point in points.items():
        in_range: list[tuple[_Site, float]] = []
        for site in sites:
            straight = straight_line_miles(point.lat, point.lon, site.lat, site.lon)
            if not _in_range(straight, drive_cap=drive_cap, straight_cap=straight_cap):
                continue
            in_range.append((site, straight))
        if not in_range:
            continue
        shares[zip_code] = _split(in_range, method=method, beta=beta)
    return shares


def _in_range(straight: float, *, drive_cap: float | None, straight_cap: float | None) -> bool:
    if straight <= _DISTANCE_TIE_MILES:
        return True
    if straight_cap is not None:
        return straight <= straight_cap
    if drive_cap is None:
        return False
    return drive_distance_miles(straight) <= drive_cap


def _split(
    in_range: Sequence[tuple[_Site, float]],
    *,
    method: Literal["gravity", "nearest"],
    beta: float | None,
) -> dict[str, float]:
    zeros = [site for site, straight in in_range if straight <= _DISTANCE_TIE_MILES]
    if zeros:
        share = 1.0 / len(zeros)
        return {site.center_id: share for site in zeros}
    if method == "nearest":
        winner = min(in_range, key=lambda item: (item[1], item[0].center_id))
        return {winner[0].center_id: 1.0}
    if beta is None:
        raise CatchmentDataError("Gravity allocation requires beta.")
    weights = {
        site.center_id: drive_distance_miles(straight) ** (-beta) for site, straight in in_range
    }
    scale = sum(weights.values())
    return {center_id: weight / scale for center_id, weight in weights.items()}


def _caps(sites: Sequence[_Site], radius_miles: float | None) -> tuple[float | None, float | None]:
    """Return ``(drive_cap, straight_cap)``. Exactly one of them is set.

    Existing centers always use the 60-mile drive cap. ``radius_miles``
    applies only when that list is empty, and it is a straight-line cutoff.
    """
    if radius_miles is not None:
        _require_radius(radius_miles)
    if sites:
        return MAX_DRIVE_MILES, None
    if radius_miles is None:
        return MAX_DRIVE_MILES, None
    return None, float(radius_miles)


def _usable_demand(demand: Sequence[ZipDemand]) -> dict[str, _ZipPoint]:
    points: dict[str, _ZipPoint] = {}
    for row in demand:
        code = _require_zip(row.zip_code)
        if code in points:
            raise CatchmentDataError(f"Demand lists ZIP {code} more than once.")
        if row.lat is None or row.lon is None or row.deliveries_per_year is None:
            continue
        lat = _coordinate("latitude", row.lat, low=-90.0, high=90.0)
        lon = _coordinate("longitude", row.lon, low=-180.0, high=180.0)
        deliveries = _require_deliveries(code, row.deliveries_per_year)
        points[code] = _ZipPoint(code, lat, lon, deliveries)
    return points


def _candidate_point(
    geo: GeoContext,
    demand: Sequence[ZipDemand],
    points: Mapping[str, _ZipPoint],
) -> _ZipPoint:
    code = _candidate_zip(geo, demand)
    point = points.get(code)
    if point is None:
        raise CatchmentDataError(
            f"ZIP {code} has no catchment data (a centroid and deliveries are both required)."
        )
    return point


def _candidate_zip(geo: GeoContext, demand: Sequence[ZipDemand]) -> str:
    wanted = _require_zip(geo.zip_code)
    codes = {_require_zip(row.zip_code) for row in demand}
    if wanted in codes:
        return wanted
    zcta = geo.zcta.strip()
    if len(zcta) == 5 and zcta.isdigit() and zcta in codes:
        return zcta
    return wanted


def _existing_sites(centers: Sequence[CenterSite]) -> tuple[_Site, ...]:
    seen: set[str] = set()
    sites: list[_Site] = []
    for center in centers:
        center_id = center.center_id.strip()
        if center_id == "" or center_id == _CANDIDATE_ID:
            raise CatchmentDataError(f"Center id {center.center_id!r} is not usable.")
        if center_id in seen:
            raise CatchmentDataError(f"Center {center_id} is listed more than once.")
        seen.add(center_id)
        name = center.name.strip()
        if name == "":
            raise CatchmentDataError(f"Center {center_id} needs a name.")
        lat = _coordinate("latitude", center.lat, low=-90.0, high=90.0)
        lon = _coordinate("longitude", center.lon, low=-180.0, high=180.0)
        sites.append(_Site(center_id, name, lat, lon))
    return tuple(sites)


def _require_beta(beta: float) -> float:
    if isinstance(beta, bool) or not isinstance(beta, (int, float)) or not math.isfinite(beta):
        raise CatchmentDataError(f"beta must be a finite number greater than 0, got {beta!r}.")
    if beta <= 0:
        raise CatchmentDataError(f"beta must be greater than 0, got {beta}.")
    return float(beta)


def _require_radius(radius_miles: float) -> float:
    if (
        isinstance(radius_miles, bool)
        or not isinstance(radius_miles, (int, float))
        or not math.isfinite(radius_miles)
        or radius_miles <= 0
    ):
        raise CatchmentDataError(
            f"radius_miles must be a finite number greater than 0, got {radius_miles!r}."
        )
    return float(radius_miles)


def _require_zip(zip_code: str) -> str:
    code = zip_code.strip()
    if len(code) != 5 or not code.isdigit():
        raise CatchmentDataError(f"ZIP must be 5 digits, got {zip_code!r}.")
    return code


def _require_deliveries(zip_code: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CatchmentDataError(f"ZIP {zip_code} deliveries must be a finite number.")
    if value < 0:
        raise CatchmentDataError(f"ZIP {zip_code} deliveries must be >= 0, got {value}.")
    return float(value)


def _coordinate(what: str, value: float, *, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CatchmentDataError(f"{what} must be a finite number, got {value!r}.")
    number = float(value)
    if number < low or number > high:
        raise CatchmentDataError(f"{what} must be between {low} and {high}, got {number}.")
    return number
