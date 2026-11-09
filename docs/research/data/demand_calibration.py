# ruff: noqa: E402
"""Demand-calibration check for the 94402 catchment. Research only.

Run from the repo root (no network, no writes):

    python3 docs/research/data/demand_calibration.py

(The script puts the repo ``src/`` on ``sys.path`` itself, so it works with
or without the editable install.)

It reads the committed demo extract and the Bay Area center seed through the
public ``dce`` loaders, reproduces the shipped gravity and nearest-center
totals, then reports:

1. Each existing center's volume before and after a 94402 candidate.
2. Extract coverage and implied Tesla volume by county, against the CEC
   county Tesla counts quoted in ``docs/research/tesla_delivery_ops_research.md``
   section 4.2.
3. Calibration cases (low / base / high): candidate deliveries, Colma after
   the candidate, and standalone and incremental NPV from ``dce.model.dcf``.

Nothing here changes ``src/dce`` or ``assumptions.yaml``. County membership
of each ZCTA below is a hand list (ZCTA to its main county); a ZCTA that
straddles a county line is counted once in its main county.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import yaml

from dce.config import assumptions_path
from dce.data.catchment_demand import (
    BAY_AREA_TESLA_BEV_SHARE,
    bay_area_zip_demand,
    delivery_center_sites,
)
from dce.data.operating_inputs import load_san_mateo_operating_inputs
from dce.geo.catchment import (
    DRIVE_CIRCUITY,
    MAX_DRIVE_MILES,
    CenterSite,
    ZipDemand,
    catchment_features,
    straight_line_miles,
)
from dce.geo.resolve import resolve_zip
from dce.model.assumptions import parse_assumptions
from dce.model.costs import build_cost_inputs
from dce.model.dcf import run_dcf_views
from dce.model.types import Scenario

CANDIDATE_ZIP = "94402"

# CEC New ZEV Sales, make = Tesla, calendar 2025 and 2026 Q1-Q3, by county.
# Quoted from tesla_delivery_ops_research.md section 4.2 (CEC xlsx, data to
# 2026-09-30, https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data,
# accessed 2026-11-08).
CEC_TESLA_2025 = {
    "San Mateo": 5296,
    "San Francisco": 3456,
    "Santa Clara": 20214,
    "Alameda": 11061,
    "Contra Costa": 5535,
    "Marin": 1259,
}
CEC_TESLA_2026_Q1_Q3 = {
    "San Mateo": 4145,
    "San Francisco": 2648,
    "Santa Clara": 14218,
    "Alameda": 7536,
    "Contra Costa": 4074,
    "Marin": 1015,
}
BAY_9_COUNTY_TESLA_2025 = 49704
BAY_9_COUNTY_BEV_2025 = 94131

SAN_MATEO = {
    "94002", "94005", "94010", "94014", "94015", "94018", "94019", "94020",
    "94025", "94027", "94028", "94030", "94037", "94038", "94044", "94060",
    "94061", "94062", "94063", "94065", "94066", "94070", "94074", "94080",
    "94128", "94401", "94402", "94403", "94404",
}  # fmt: skip
SANTA_CLARA_EXTRA = {
    "94022", "94024", "94040", "94041", "94043", "94085", "94086", "94087",
    "94089", "94301", "94303", "94304", "94305", "94306",
}  # fmt: skip
SANTA_CRUZ = {
    "95003", "95005", "95006", "95010", "95017", "95018", "95019", "95041",
    "95060", "95062", "95064", "95065", "95066", "95073", "95076",
}  # fmt: skip
SAN_JOAQUIN = {"95304", "95376", "95377", "95391"}
CONTRA_COSTA_94 = {
    "94505", "94506", "94507", "94509", "94511", "94513", "94514", "94516",
    "94517", "94518", "94519", "94520", "94521", "94523", "94525", "94526",
    "94528", "94530", "94531", "94547", "94548", "94549", "94553", "94556",
    "94561", "94563", "94564", "94565", "94569", "94572", "94582", "94583",
    "94595", "94596", "94597", "94598", "94707", "94708",
}  # fmt: skip
SOLANO = {"94510", "94533", "94534", "94535", "94571", "94585", "94589", "94590", "94591", "94592"}
NAPA = {"94503", "94558", "94559"}
SONOMA = {"94952", "94954", "95476"}


def county_of(zip_code: str) -> str:
    """Main county of a Bay Area extract ZCTA (hand list, see module doc)."""
    if zip_code in SAN_MATEO:
        return "San Mateo"
    if zip_code.startswith("941"):
        return "San Francisco"
    if zip_code in SANTA_CRUZ:
        return "Santa Cruz"
    if zip_code in SAN_JOAQUIN:
        return "San Joaquin"
    if zip_code in SANTA_CLARA_EXTRA or zip_code.startswith(("950", "951")):
        return "Santa Clara"
    if zip_code in SOLANO:
        return "Solano"
    if zip_code in NAPA:
        return "Napa"
    if zip_code in SONOMA:
        return "Sonoma"
    if zip_code in CONTRA_COSTA_94 or zip_code.startswith("948"):
        return "Contra Costa"
    if zip_code.startswith(("945", "946", "947")):
        return "Alameda"
    if zip_code.startswith("949"):
        return "Marin"
    return "Other"


def center_volumes(
    demand: Sequence[ZipDemand],
    centers: Sequence[CenterSite],
    *,
    method: str,
    beta: float = 2.0,
) -> dict[str, float]:
    """Deliveries per site, same rule as ``dce.geo.catchment`` (cap, ties, beta).

    The shipped module reports only the candidate and what it takes from each
    center, so this mirrors its private share rule to get per-center totals.
    The candidate total is cross-checked against ``catchment_features``.
    """
    totals: dict[str, float] = defaultdict(float)
    for row in demand:
        assert row.lat is not None and row.lon is not None and row.deliveries_per_year
        in_range = []
        for site in centers:
            miles = straight_line_miles(row.lat, row.lon, site.lat, site.lon)
            if miles <= 1e-9 or miles * DRIVE_CIRCUITY <= MAX_DRIVE_MILES:
                in_range.append((site.center_id, miles))
        if not in_range:
            totals["unserved"] += row.deliveries_per_year
            continue
        zeros = [cid for cid, miles in in_range if miles <= 1e-9]
        if zeros:
            for cid in zeros:
                totals[cid] += row.deliveries_per_year / len(zeros)
            continue
        if method == "nearest":
            cid = min(in_range, key=lambda item: (item[1], item[0]))[0]
            totals[cid] += row.deliveries_per_year
            continue
        weights = {cid: (miles * DRIVE_CIRCUITY) ** -beta for cid, miles in in_range}
        scale = math.fsum(weights.values())
        for cid, weight in weights.items():
            totals[cid] += row.deliveries_per_year * weight / scale
    return dict(totals)


def scaled(demand: Iterable[ZipDemand], factor: Mapping[str, float] | float) -> list[ZipDemand]:
    """Multiply each ZIP's deliveries by a flat factor or a county factor."""
    out = []
    for row in demand:
        assert row.deliveries_per_year is not None
        f = factor if isinstance(factor, float) else factor.get(county_of(row.zip_code), 1.0)
        out.append(replace(row, deliveries_per_year=row.deliveries_per_year * f))
    return out


def dcf_npvs(steady: float) -> tuple[float, float, float | None]:
    """Standalone NPV, incremental NPV, standalone IRR at ``steady`` deliveries.

    Same path as ``dce.orchestrator.estimate`` (demo rent and rates, baseline
    scenario), with the steady volume substituted.
    """
    raw = yaml.safe_load(assumptions_path().read_text(encoding="utf-8"))
    a = parse_assumptions(raw)
    rates = load_san_mateo_operating_inputs()
    scenario = Scenario(
        vehicle_mix=dict(a.vehicle_mix), wage_shock=0.0, rent_shock=0.0, delivery_shock=0.0
    )
    costs = build_cost_inputs(
        a,
        rent_psf_month=rates.rent_psf_month,
        wage_annual=a.labor.fallback_wage_hourly * a.labor.paid_hours_per_fte,
        energy_rate_kwh=rates.energy_rate_kwh,
        demand_rate_kw=rates.demand_rate_kw,
        annual_deliveries=steady,
    )
    views = run_dcf_views(costs, a, steady_deliveries=steady, scenario=scenario)
    return views.standalone.npv, views.incremental.npv, views.standalone.irr


def main() -> None:
    geo = resolve_zip(CANDIDATE_ZIP)
    demand = list(bay_area_zip_demand())
    centers = list(delivery_center_sites())
    candidate_row = next(r for r in demand if r.zip_code == CANDIDATE_ZIP)
    assert candidate_row.lat is not None and candidate_row.lon is not None
    candidate = CenterSite("candidate", "San Mateo candidate", candidate_row.lat, candidate_row.lon)

    total_tesla = math.fsum(r.deliveries_per_year or 0.0 for r in demand)
    total_bev = total_tesla / BAY_AREA_TESLA_BEV_SHARE
    print(f"Extract: {len(demand)} ZCTAs, BEV 2025 {total_bev:,.0f}, Tesla {total_tesla:,.0f}")
    print(f"Tesla/BEV share used: {BAY_AREA_TESLA_BEV_SHARE:.4f}")
    print(f"Centers: {len(centers)} ({', '.join(c.center_id for c in centers)})")

    # 1. Per-center volumes.
    print("\n== Per-center volumes (deliveries/yr) ==")
    print(f"{'center':16} {'grav before':>11} {'grav after':>10} {'taken':>7}"
          f" {'near before':>11} {'near after':>10} {'taken':>7}")  # fmt: skip
    gb = center_volumes(demand, centers, method="gravity")
    ga = center_volumes(demand, [*centers, candidate], method="gravity")
    nb = center_volumes(demand, centers, method="nearest")
    na = center_volumes(demand, [*centers, candidate], method="nearest")
    for cid in [c.center_id for c in centers] + ["candidate", "unserved"]:
        print(
            f"{cid:16} {gb.get(cid, 0):11,.0f} {ga.get(cid, 0):10,.0f}"
            f" {gb.get(cid, 0) - ga.get(cid, 0):7,.0f} {nb.get(cid, 0):11,.0f}"
            f" {na.get(cid, 0):10,.0f} {nb.get(cid, 0) - na.get(cid, 0):7,.0f}"
        )
    features = catchment_features(geo, centers, demand)
    print(
        f"Package check: gravity {features.gravity.total_deliveries_per_year:,.1f}"
        f" (mirror {ga['candidate']:,.1f}); nearest"
        f" {features.nearest.total_deliveries_per_year:,.1f} (mirror {na['candidate']:,.1f})"
    )
    for row in features.gravity.taken_from:
        print(f"  gravity taken from {row.center_id}: {row.deliveries_per_year:,.0f}")

    # 2. County coverage.
    print("\n== County coverage (2025) ==")
    by_county: dict[str, float] = defaultdict(float)
    for r in demand:
        by_county[county_of(r.zip_code)] += r.deliveries_per_year or 0.0
    factors: dict[str, float] = {}
    print(
        f"{'county':14} {'extract Tesla':>13} {'CEC Tesla':>9} {'factor':>7} {'2026 run-rate':>13}"
    )
    for county in sorted(by_county, key=lambda c: -by_county[c]):
        model = by_county[county]
        cec = CEC_TESLA_2025.get(county)
        run = CEC_TESLA_2026_Q1_Q3.get(county)
        if cec is not None and run is not None:
            factors[county] = cec / model
            print(f"{county:14} {model:13,.0f} {cec:9,} {cec / model:7.3f} {run * 4 / 3:13,.0f}")
        else:
            print(f"{county:14} {model:13,.0f} {'n/a':>9}")
    bay = math.fsum(v for k, v in by_county.items() if k not in {"Santa Cruz", "San Joaquin"})
    print(f"9-county subset of extract: Tesla {bay:,.0f} vs CEC {BAY_9_COUNTY_TESLA_2025:,}"
          f" ({bay / BAY_9_COUNTY_TESLA_2025:.1%})")  # fmt: skip

    # 3. Calibration cases.
    print("\n== Calibration cases ==")
    county_demand = scaled(demand, factors)
    cases = {
        "shipped (1.00, uniform share)": (demand, 1.0),
        "county-anchored only": (county_demand, 1.0),
        "low  (county x 1.00)": (county_demand, 1.00),
        "base (county x 1.10)": (county_demand, 1.10),
        "high (county x 1.30)": (county_demand, 1.30),
        "stress (county x 3.00)": (county_demand, 3.00),
    }
    for label, (rows, flat) in cases.items():
        rows_scaled = scaled(rows, flat)
        f = catchment_features(geo, centers, rows_scaled)
        g = f.gravity.total_deliveries_per_year
        n = f.nearest.total_deliveries_per_year
        colma_before = center_volumes(rows_scaled, centers, method="gravity")["colma"]
        colma_after = center_volumes(rows_scaled, [*centers, candidate], method="gravity")["colma"]
        colma_near = center_volumes(rows_scaled, centers, method="nearest")["colma"]
        sa, inc, irr = dcf_npvs(g)
        irr_text = "n/a" if irr is None else f"{irr:.1%}"
        print(
            f"{label:30} candidate grav {g:6,.0f} near {n:6,.0f} | Colma grav {colma_before:6,.0f}"
            f" -> {colma_after:6,.0f}, near-before {colma_near:6,.0f} | NPV standalone"
            f" {sa / 1e6:+6.2f}M IRR {irr_text} incremental {inc / 1e6:+6.2f}M"
        )


if __name__ == "__main__":
    main()
