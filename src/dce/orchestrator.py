"""ZIP-in, estimate-out orchestration.

Contract
--------
``estimate(zip_code, scenario=None, overrides=None) -> EstimateResult``

One call runs the whole pipeline. The only required argument is a 5-digit
US ZIP. The steps are:

1. Resolve the ZIP to county, CBSA, and state.
2. Load that ZIP's local inputs (ACS, OEWS SOC 49-3023, resolved rent, CEC
   or the national Tesla fallback). See ``docs/contracts/zip_data.md``.
3. Build the gravity catchment (beta 2) on nationwide origin demand.
   Nearest-center is the low case. The competing sites are the US Find Us
   delivery list.
4. Feed the gravity deliveries per year into the cost model.
5. Run both DCF benefit views at that steady volume. The default discount
   rate is the Tesla WACC on the assumptions table, 13.6%. The building
   stays 25,000 square feet.

California origin demand is the CEC ZIP battery-electric count times the
county Tesla share, annualized when the seed year is short a quarter, then
times the base handover factor 1.10. Other states split the Cox/KBB 2025
US Tesla total, minus the 2025 California CEC total, by ACS households and
income. Utility rates stay the San Mateo PG&E B-10 figures until a rate
loader exists. Every resolved input is on ``EstimateResult.provenance``.

There is no network call and no prompt. ``overrides`` may carry
``rent_psf_month``. Do not import ``dce.extract.pdf_llm``.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from dce.config import assumptions_path, user_data_dir
from dce.data.catchment_demand import delivery_center_sites
from dce.data.ingest.bls_oews import OEWS_SOC_AUTO_TECH
from dce.data.ingest.zev_sales import INCOME_ELASTICITY, INCOME_REFERENCE
from dce.data.national_demand import (
    CA_TESLA_SALES_2025,
    US_TESLA_SALES_2025,
    NationalDemand,
    build_national_demand,
)
from dce.data.operating_inputs import OperatingInputs, load_san_mateo_operating_inputs
from dce.data.zip_local import ZipLocalData, load_zip_local
from dce.data.zip_seed import load_zip_seed
from dce.geo.catchment import (
    DRIVE_CIRCUITY,
    MAX_DRIVE_MILES,
    CatchmentCase,
    CatchmentFeatures,
    CenterSite,
    ZipDemand,
    catchment_features,
    straight_line_miles,
)
from dce.geo.resolve import resolve_zip
from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.costs import CostInputs, build_cost_inputs
from dce.model.types import (
    CatchmentCaseSummary,
    CatchmentSummary,
    CatchmentZipVolume,
    CenterVolumeTaken,
    EstimateResult,
    GeoContext,
    InputProvenance,
    NearbyCenter,
    Scenario,
)
from dce.scenarios.grid import outcome_scenarios, run_scenario, run_scenario_grid
from dce.scenarios.tornado import TornadoBar, TornadoInputs, dcf_tornado
from dce.scenarios.types import NamedScenario
from dce.storage.connection import enable_wal, get_connection
from dce.storage.repository import national_seed_loaded

# Optional advanced overrides. ZIP alone must still run.
Overrides = Mapping[str, object]
_RENT_OVERRIDE = "rent_psf_month"
_STRAIGHT_CAP_MILES = MAX_DRIVE_MILES / DRIVE_CIRCUITY + 0.05
_CENTER_CAP_MILES = _STRAIGHT_CAP_MILES * 2
_SEED_FETCHED_AT = "2026-11-09T00:00:00Z"
_LOW_RENT_TIERS = frozenset({"national", "hud_safmr", "acs_gross_rent"})


class EstimateDataError(ValueError):
    """A local input the estimate needs is missing or not usable."""


@dataclass(frozen=True)
class PreparedEstimate:
    """Resolved inputs for one ZIP, before scenario shocks."""

    assumptions: ModelAssumptions
    geo: GeoContext
    costs: CostInputs
    steady: float
    catchment: CatchmentSummary
    provenance: tuple[InputProvenance, ...]
    nearby_centers: tuple[NearbyCenter, ...]
    scenario: Scenario


@dataclass(frozen=True)
class ZipEvaluation:
    """Base, low, and high outcomes plus the standalone NPV tornado."""

    base: EstimateResult
    scenarios: dict[str, EstimateResult]
    tornado: tuple[TornadoBar, ...]


@dataclass
class _Bundle:
    data_dir: Path
    conn: sqlite3.Connection
    assumptions: ModelAssumptions
    centers: tuple[CenterSite, ...]
    demand: NationalDemand
    index: _Grid
    utilities: OperatingInputs


class _Grid:
    """Degree cells over origin ZIPs. The exact mile test happens after."""

    def __init__(self, points: tuple[tuple[str, float, float, float], ...]) -> None:
        cells: dict[tuple[int, int], list[tuple[str, float, float, float]]] = {}
        for point in points:
            key = (math.floor(point[1]), math.floor(point[2]))
            cells.setdefault(key, []).append(point)
        self._cells = cells

    def around(
        self, lat: float, lon: float, radius_miles: float
    ) -> tuple[tuple[str, float, float, float], ...]:
        cos = max(0.2, math.cos(math.radians(lat)))
        dlat = radius_miles / 60.0 + 0.25
        dlon = radius_miles / (50.0 * cos) + 0.25
        lat0 = math.floor(lat - dlat)
        lat1 = math.floor(lat + dlat)
        lon0 = math.floor(lon - dlon)
        lon1 = math.floor(lon + dlon)
        found: list[tuple[str, float, float, float]] = []
        for cell_lat in range(int(lat0), int(lat1) + 1):
            for cell_lon in range(int(lon0), int(lon1) + 1):
                found.extend(self._cells.get((cell_lat, cell_lon), ()))
        return tuple(found)


_BUNDLES: dict[str, _Bundle] = {}


def warm_bundle(data_dir: Path | None = None) -> _Bundle:
    """Load the seed, origin demand, and centers once for this process."""
    return _bundle(data_dir)


def estimate(
    zip_code: str,
    scenario: Scenario | None = None,
    overrides: Overrides | None = None,
    *,
    data_dir: Path | None = None,
) -> EstimateResult:
    """Run catchment, cost, and both DCF views for ``zip_code``."""
    prepared = _prepare(zip_code, overrides, data_dir=data_dir, persist_rent=True)
    if scenario is None:
        named = _base_named(prepared.assumptions)
    else:
        named = NamedScenario("custom", "Custom", scenario)
    return _run(prepared, named)


def evaluate_zip(
    zip_code: str,
    *,
    data_dir: Path | None = None,
    persist_rent: bool = False,
) -> ZipEvaluation:
    """Return low, base, and high outcomes and the standalone tornado.

    The catchment is built once. ``persist_rent`` is off so a batch does not
    commit one rent row per ZIP.
    """
    prepared = _prepare(zip_code, None, data_dir=data_dir, persist_rent=persist_rent)
    named = outcome_scenarios(prepared.assumptions)
    results = run_scenario_grid(
        prepared.geo,
        prepared.steady,
        prepared.costs,
        named,
        prepared.assumptions,
        catchment=prepared.catchment,
        provenance=prepared.provenance,
        nearby_centers=prepared.nearby_centers,
    )
    scenarios = {row.scenario_id: row.result for row in results}
    bars = dcf_tornado(
        TornadoInputs(
            costs=prepared.costs,
            assumptions=prepared.assumptions,
            steady_deliveries=prepared.steady,
            scenario=prepared.scenario,
        )
    )
    return ZipEvaluation(base=scenarios["base"], scenarios=scenarios, tornado=tuple(bars))


def _run(prepared: PreparedEstimate, named: NamedScenario) -> EstimateResult:
    return run_scenario(
        prepared.geo,
        prepared.steady,
        prepared.costs,
        named,
        prepared.assumptions,
        catchment=prepared.catchment,
        provenance=prepared.provenance,
        nearby_centers=prepared.nearby_centers,
    ).result


def _prepare(
    zip_code: str,
    overrides: Overrides | None,
    *,
    data_dir: Path | None,
    persist_rent: bool,
) -> PreparedEstimate:
    geo = resolve_zip(zip_code)
    bundle = _bundle(data_dir)
    local = load_zip_local(geo.zip_code, bundle.conn, persist_rent=persist_rent)
    place = bundle.demand.places.get(geo.zip_code)
    if place is None or place.lat is None or place.lon is None:
        zcta = geo.zcta
        raise EstimateDataError(
            f"ZIP {geo.zip_code} has no 2024 Gazetteer internal point for ZCTA {zcta}."
        )
    points = _demand_rows(bundle, place.lat, place.lon, geo.zip_code)
    centers = _centers_near(bundle.centers, place.lat, place.lon)
    features = catchment_features(geo, centers, points)
    steady = features.gravity.total_deliveries_per_year
    if steady <= 0.0:
        raise EstimateDataError(
            f"ZIP {geo.zip_code} has no deliveries inside the 60-mile catchment, "
            "so cost per delivery is undefined."
        )
    rent, rent_row = _rent(local, overrides)
    wage, wage_row = _wage(local, bundle.assumptions)
    utilities = bundle.utilities
    costs = build_cost_inputs(
        bundle.assumptions,
        rent_psf_month=rent,
        wage_annual=wage,
        energy_rate_kwh=utilities.energy_rate_kwh,
        demand_rate_kw=utilities.demand_rate_kw,
        annual_deliveries=steady,
    )
    catchment = _summarize(features)
    nearby = _nearby(bundle.centers, place.lat, place.lon, catchment)
    provenance = _provenance(
        local,
        bundle.demand,
        utilities,
        rent_row,
        wage_row,
        steady,
    )
    return PreparedEstimate(
        assumptions=bundle.assumptions,
        geo=geo,
        costs=costs,
        steady=steady,
        catchment=catchment,
        provenance=provenance,
        nearby_centers=nearby,
        scenario=_baseline_scenario(bundle.assumptions),
    )


def _bundle(data_dir: Path | None) -> _Bundle:
    directory = user_data_dir() if data_dir is None else data_dir
    key = str(directory.resolve())
    cached = _BUNDLES.get(key)
    if cached is not None:
        return cached
    conn = get_connection(directory)
    enable_wal(conn)
    if not national_seed_loaded(conn):
        load_zip_seed(conn, fetched_at=_SEED_FETCHED_AT)
    assumptions = parse_assumptions(_load_assumptions())
    demand = build_national_demand(conn, handover_factor=assumptions.demand.handover_factor)
    indexed: list[tuple[str, float, float, float]] = []
    for zip_code, deliveries in demand.deliveries.items():
        located = demand.places.get(zip_code)
        if located is None or located.lat is None or located.lon is None:
            continue
        indexed.append((zip_code, located.lat, located.lon, deliveries))
    points = tuple(indexed)
    bundle = _Bundle(
        data_dir=directory,
        conn=conn,
        assumptions=assumptions,
        centers=delivery_center_sites(),
        demand=demand,
        index=_Grid(points),
        utilities=load_san_mateo_operating_inputs(),
    )
    _BUNDLES[key] = bundle
    return bundle


def _demand_rows(bundle: _Bundle, lat: float, lon: float, zip_code: str) -> tuple[ZipDemand, ...]:
    rows: list[ZipDemand] = []
    seen = False
    for code, point_lat, point_lon, deliveries in bundle.index.around(
        lat, lon, _STRAIGHT_CAP_MILES
    ):
        if straight_line_miles(lat, lon, point_lat, point_lon) > _STRAIGHT_CAP_MILES:
            continue
        rows.append(ZipDemand(code, point_lat, point_lon, deliveries))
        seen = seen or code == zip_code
    if not seen:
        own = bundle.demand.deliveries.get(zip_code, 0.0)
        rows.append(ZipDemand(zip_code, lat, lon, own))
    return tuple(rows)


def _centers_near(
    centers: tuple[CenterSite, ...], lat: float, lon: float
) -> tuple[CenterSite, ...]:
    return tuple(
        center
        for center in centers
        if straight_line_miles(lat, lon, center.lat, center.lon) <= _CENTER_CAP_MILES
    )


def _nearby(
    centers: tuple[CenterSite, ...],
    lat: float,
    lon: float,
    catchment: CatchmentSummary,
) -> tuple[NearbyCenter, ...]:
    taken = {row.center_id: row.deliveries_per_year for row in catchment.gravity.taken_from}
    rows: list[NearbyCenter] = []
    for center in centers:
        straight = straight_line_miles(lat, lon, center.lat, center.lon)
        drive = straight * DRIVE_CIRCUITY
        if straight > 1e-9 and drive > MAX_DRIVE_MILES:
            continue
        rows.append(
            NearbyCenter(
                center_id=center.center_id,
                name=center.name,
                straight_line_miles=straight,
                drive_miles=drive,
                deliveries_taken_per_year=taken.get(center.center_id, 0.0),
            )
        )
    rows.sort(key=lambda row: (row.drive_miles, row.center_id))
    return tuple(rows)


def _load_assumptions() -> dict[str, object]:
    path = assumptions_path()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EstimateDataError(f"Could not read assumptions: {path}.") from exc
    except yaml.YAMLError as exc:
        raise EstimateDataError(f"Assumptions file is not valid YAML: {path}.") from exc
    if not isinstance(loaded, dict):
        raise EstimateDataError("Assumptions file must be a mapping.")
    return {str(key): value for key, value in loaded.items()}


def _baseline_scenario(assumptions: ModelAssumptions) -> Scenario:
    return Scenario(
        vehicle_mix=dict(assumptions.vehicle_mix),
        wage_shock=0.0,
        rent_shock=0.0,
        delivery_shock=0.0,
    )


def _base_named(assumptions: ModelAssumptions) -> NamedScenario:
    for named in outcome_scenarios(assumptions):
        if named.scenario_id == "base":
            return named
    raise EstimateDataError("The assumptions file has no base outcome scenario.")


def _rent(local: ZipLocalData, overrides: Overrides | None) -> tuple[float, InputProvenance]:
    if overrides:
        unknown = sorted(set(overrides) - {_RENT_OVERRIDE})
        if unknown:
            raise EstimateDataError(
                "Unknown override "
                + ", ".join(unknown)
                + ". The optional override is rent_psf_month."
            )
        if _RENT_OVERRIDE in overrides:
            value = _finite_rent(overrides[_RENT_OVERRIDE])
            return value, InputProvenance(
                name="rent_psf_month",
                value=value,
                unit="usd_per_sf_per_month",
                source="override",
                geography_level="zip",
                geography_id=local.geo.zip_code,
                fallback=False,
                detail="Caller override. The rent resolver was not used.",
            )
    if local.rent is None:
        message = local.rent_error or f"ZIP {local.geo.zip_code} has no resolved rent."
        raise EstimateDataError(message)
    resolved = local.rent
    level, geo_id = _rent_geography(local, resolved.tier)
    return resolved.rent_psf_month, InputProvenance(
        name="rent_psf_month",
        value=resolved.rent_psf_month,
        unit="usd_per_sf_per_month",
        source=resolved.tier,
        geography_level=level,
        geography_id=geo_id,
        fallback=resolved.tier in _LOW_RENT_TIERS or resolved.confidence == "low",
        detail=(
            f"{resolved.citation} Confidence {resolved.confidence}. as_of {resolved.as_of}. "
            f"Property type {resolved.property_type}."
        ),
    )


def _rent_geography(local: ZipLocalData, tier: str) -> tuple[str, str]:
    if tier == "acs_gross_rent":
        return "zcta", local.geo.zcta
    if tier in {"zip_adjusted_cbsa", "cbsa_raw"}:
        return "cbsa", local.geo.cbsa
    if tier == "county_gsa":
        return "county", local.geo.county_fips
    if tier == "state":
        return "state", local.geo.state
    return "national", "US"


def _wage(local: ZipLocalData, assumptions: ModelAssumptions) -> tuple[float, InputProvenance]:
    match = next(
        (
            row
            for row in local.wages
            if row.soc == OEWS_SOC_AUTO_TECH and row.mean_annual is not None
        ),
        None,
    )
    if match is None or match.mean_annual is None:
        annual = assumptions.labor.fallback_wage_hourly * assumptions.labor.paid_hours_per_fte
        return annual, InputProvenance(
            name="wage_annual",
            value=annual,
            unit="usd_per_year",
            source="assumptions.labor.fallback_wage_hourly",
            geography_level="national",
            geography_id="US",
            fallback=True,
            detail=(
                "No OEWS SOC 49-3023 mean was stored for this area or the nation. "
                f"Hourly fallback {assumptions.labor.fallback_wage_hourly:g} "
                f"times {assumptions.labor.paid_hours_per_fte:g} paid hours."
            ),
        )
    metro = local.wage_basis == "cbsa"
    return match.mean_annual, InputProvenance(
        name="wage_annual",
        value=match.mean_annual,
        unit="usd_per_year",
        source="bls_oews",
        geography_level="cbsa" if metro else "national",
        geography_id=local.oews_area,
        fallback=not metro,
        detail=(
            f"BLS OEWS May 2025 SOC {OEWS_SOC_AUTO_TECH} mean annual wage, "
            f"area {local.oews_area} ({match.area_name}), as_of {match.as_of}. "
            f"Basis {local.wage_basis}. Micropolitan and non-metro ZIPs use the "
            "national row. This SOC is the series published for every metro, "
            "not the delivery-role mix."
        ),
    )


def _provenance(
    local: ZipLocalData,
    demand: NationalDemand,
    utilities: OperatingInputs,
    rent_row: InputProvenance,
    wage_row: InputProvenance,
    steady: float,
) -> tuple[InputProvenance, ...]:
    place = demand.places.get(local.geo.zip_code)
    state = local.geo.state if place is None else place.state
    own = demand.deliveries.get(local.geo.zip_code, 0.0)
    rows = [
        rent_row,
        wage_row,
        _utility("energy_rate_kwh", utilities.energy_rate_kwh, "usd_per_kwh", utilities),
        _utility("demand_rate_kw", utilities.demand_rate_kw, "usd_per_kw_per_month", utilities),
        _acs(local, "population", local.population, "people"),
        _acs(local, "households", local.households, "households"),
        _acs(local, "median_hh_income", local.median_hh_income, "usd_per_year"),
        _acs(local, "median_gross_rent", local.median_gross_rent, "usd_per_month"),
        _acs(local, "median_home_value", local.median_home_value, "usd"),
        _acs(local, "vehicles_available", local.vehicles_available, "vehicles"),
        _acs(
            local,
            "mean_commute",
            local.mean_commute,
            "minutes",
            missing="ACS S0801 mean commute is not in the national summary file.",
        ),
        *_demand_provenance(local, demand, state, own, steady),
    ]
    return tuple(rows)


def _demand_provenance(
    local: ZipLocalData,
    demand: NationalDemand,
    state: str,
    own: float,
    steady: float,
) -> tuple[InputProvenance, InputProvenance, InputProvenance, InputProvenance]:
    income_missing = local.median_hh_income is None or local.median_hh_income <= 0
    if state == "CA":
        listed = ", ".join(str(quarter) for quarter in demand.quarters) or "none"
        detail = (
            f"CEC New ZEV Sales as of {demand.cec_as_of or 'the stored file'}, "
            f"quarters {listed}. ZIP battery-electric sales times Tesla's share of "
            f"battery-electric sales in the county, times {demand.annualization:.6g} "
            f"to fill a 4-quarter year, then handover {demand.handover_factor:.2f}. "
            "A county with no CEC Tesla row keeps the 2025 9-county share "
            "49,704 / 94,131."
        )
        if own <= 0.0:
            detail += " This ZIP has no battery-electric row, so its own origin demand is 0."
        source = "cec"
        level = "county"
        geo_id = local.geo.county_fips
        origin_fallback = own <= 0.0
        annualization_fallback = demand.annualization != 1.0
        annualization = demand.annualization
    else:
        detail = (
            "No California Energy Commission file covers this state, and the seed "
            "does not include a state Tesla total. "
            f"Cox/KBB 2025 US Tesla sales {US_TESLA_SALES_2025:,.0f} minus CEC 2025 "
            f"California Tesla sales {CA_TESLA_SALES_2025:,.0f} are allocated by ACS "
            f"households and income elasticity {INCOME_ELASTICITY:g} "
            f"(reference ${INCOME_REFERENCE:,.0f}). The EV-share term is 1 because "
            "the national file has no EV stock. "
            f"Handover factor {demand.handover_factor:.2f}. "
            "Only a ZIP that is its own ZCTA receives households, so a PO box is "
            "not a second copy."
        )
        if income_missing:
            detail += (
                " This ZIP's median income is suppressed, so the allocator used the reference."
            )
        source = "cox_kbb_2025"
        level = "national"
        geo_id = "US"
        origin_fallback = True
        annualization_fallback = False
        annualization = 1.0
    return (
        InputProvenance(
            "zip_origin_deliveries",
            own,
            "deliveries_per_year",
            source,
            level,
            geo_id,
            origin_fallback,
            detail,
        ),
        InputProvenance(
            "handover_factor",
            demand.handover_factor,
            "ratio",
            "assumptions.demand.handover_factor",
            "national",
            "US",
            False,
            "Base handover factor. 1.10 and 1.30 are assumptions: no public source "
            "counts used-car handovers.",
        ),
        InputProvenance(
            "demand_annualization",
            annualization,
            "ratio",
            source,
            "state" if state == "CA" else "national",
            state if state == "CA" else "US",
            annualization_fallback,
            "Partial-year CEC counts are scaled to four quarters with a flat factor. "
            "The Cox/KBB US figure is already a calendar year.",
        ),
        InputProvenance(
            "catchment_deliveries",
            steady,
            "deliveries_per_year",
            source,
            level,
            geo_id,
            origin_fallback,
            "Huff gravity, beta 2, straight-line miles times 1.25, 60-mile cap, "
            "net of the US Find Us delivery list. This is the unshocked steady volume.",
        ),
    )


def _utility(name: str, value: float, unit: str, utilities: OperatingInputs) -> InputProvenance:
    return InputProvenance(
        name=name,
        value=value,
        unit=unit,
        source="pge_schedule_b10",
        geography_level="demo",
        geography_id="san_mateo",
        fallback=True,
        detail=(
            f"{utilities.energy_citation} as_of {utilities.as_of}. "
            "No ZIP utility-rate loader is wired, so every ZIP uses this published "
            "PG&E B-10 figure."
        ),
    )


def _acs(
    local: ZipLocalData,
    name: str,
    value: float | None,
    unit: str,
    *,
    missing: str = "ACS did not publish this field for the ZCTA.",
) -> InputProvenance:
    return InputProvenance(
        name=name,
        value=value,
        unit=unit,
        source="acs_2024_5yr",
        geography_level="zcta",
        geography_id=local.geo.zcta,
        fallback=value is None,
        detail=(
            missing
            if value is None
            else f"ACS 2024 5-year ZCTA {local.geo.zcta}, year {local.acs_year}."
        ),
    )


def _finite_rent(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EstimateDataError(f"rent_psf_month must be a finite number, got {value!r}.")
    if value < 0:
        raise EstimateDataError(f"rent_psf_month must be >= 0, got {value}.")
    return float(value)


def _summarize(features: CatchmentFeatures) -> CatchmentSummary:
    return CatchmentSummary(
        zip_code=features.zip_code,
        beta=features.beta,
        gravity=_case(features.gravity),
        nearest=_case(features.nearest),
    )


def _case(case: CatchmentCase) -> CatchmentCaseSummary:
    return CatchmentCaseSummary(
        method=case.method,
        beta=case.beta,
        zips=tuple(
            CatchmentZipVolume(row.zip_code, row.deliveries_per_year, row.share)
            for row in case.zips
        ),
        deliveries_per_year=case.total_deliveries_per_year,
        taken_from=tuple(
            CenterVolumeTaken(row.center_id, row.name, row.deliveries_per_year)
            for row in case.taken_from
        ),
    )


__all__ = [
    "EstimateDataError",
    "PreparedEstimate",
    "ZipEvaluation",
    "estimate",
    "evaluate_zip",
    "warm_bundle",
]
