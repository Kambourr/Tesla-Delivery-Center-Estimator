# Module Contracts

Pure model functions must not import `requests`, the GUI, storage, ingest, or `extract.pdf_llm`. Scenario expansion lives in `dce.scenarios` and is also pure. Shared dataclasses stay in `dce.model.types` so the model does not import `scenarios`.

## `dce.model.types`

```python
@dataclass(frozen=True)
class Scenario:
    vehicle_mix: dict[str, float]
    wage_shock: float  # -0.2..0.2
    rent_shock: float = 0.0
    delivery_shock: float = 0.0


@dataclass(frozen=True)
class GeoContext:
    zip_code: str
    zcta: str
    county_fips: str
    cbsa: str
    state: str


@dataclass(frozen=True)
class DemandInputs:
    population: float
    median_hh_income: float
    ev_stock: float
    total_ldv: float
    mean_commute: float
    catchment_population: float


@dataclass(frozen=True)
class CostInputs:
    sqft: float
    rent_psf_month: float
    opex_load: float
    wage_annual: float
    wage_load: float
    headcount: float
    kwh_per_year: float
    energy_rate_kwh: float
    demand_kw: float
    demand_rate_kw: float
    property_tax_annual: float
    capex_total: float
    capex_years: float
    other_opex_annual: float


@dataclass(frozen=True)
class Driver:
    name: str
    usd: float
    share: float


@dataclass(frozen=True)
class CatchmentZipVolume:
    zip_code: str
    deliveries_per_year: float
    share: float


@dataclass(frozen=True)
class CenterVolumeTaken:
    center_id: str
    name: str
    deliveries_per_year: float


@dataclass(frozen=True)
class CatchmentCaseSummary:
    method: Literal["gravity", "nearest"]
    beta: float | None
    zips: tuple[CatchmentZipVolume, ...]
    deliveries_per_year: float
    taken_from: tuple[CenterVolumeTaken, ...]


@dataclass(frozen=True)
class CatchmentSummary:
    zip_code: str
    beta: float
    gravity: CatchmentCaseSummary  # base; feeds the cost model and the DCF
    nearest: CatchmentCaseSummary  # low case


@dataclass(frozen=True)
class EstimateResult:
    geo: GeoContext
    scenario: Scenario
    cost_per_delivery: float
    annualized_total_cost: float
    estimated_annual_deliveries: float
    components: dict[str, float]
    drivers: list[Driver]
    map_path: str | None
    catchment: CatchmentSummary | None = None  # gravity base + nearest low case
    dcf: DcfViews | None = None  # M3.5b; standalone + incremental lenses (ADR-0005)
    provenance: tuple[InputProvenance, ...] = ()  # source, geography, fallback, pre-shock value
    nearby_centers: tuple[NearbyCenter, ...] = ()  # delivery centers inside the 60-mile drive cap
```

## Signatures

```python
# model/demand.py
def estimate_annual_deliveries(demand: DemandInputs, assumptions: Assumptions) -> float: ...


# model/costs.py
def annualized_components(costs: CostInputs, scenario: Scenario) -> dict[str, float]: ...
def cost_per_delivery(components: dict[str, float], deliveries: float) -> float: ...


# model/drivers.py
def top_drivers(components: dict[str, float], n: int = 3) -> list[Driver]: ...


# M3 additions (pure; same package)
# model/assumptions.py
def parse_assumptions(raw: Assumptions | ModelAssumptions) -> ModelAssumptions: ...
# model/demand.py
def apply_delivery_shock(deliveries: float, scenario: Scenario) -> float: ...
# model/costs.py
def build_cost_inputs(
    assumptions, *, rent_psf_month, wage_annual, energy_rate_kwh, demand_rate_kw, annual_deliveries
) -> CostInputs: ...


# scenarios/grid.py
def expand_default_scenarios(base_mix: dict[str, float]) -> list[Scenario]: ...
def run_scenario_grid(geo, demand, costs, scenarios, assumptions) -> list[EstimateResult]: ...


# scenarios/robustness.py
def spearman_rank_corr(ranks_a: list[str], ranks_b: list[str]) -> float: ...
def driver_rank_stability(results: list[EstimateResult], baseline_id: str) -> dict[str, float]: ...


# M3.5b additions (pure; dce.model)
# model/costs.py
def upfront_capex(
    assumptions, sqft: float | None = None
) -> tuple[float, float]: ...  # (improvements, equipment)
# model/dcf.py
def build_dcf_inputs(assumptions, *, benefit_mode: BenefitMode | None = None) -> DcfInputs: ...
def run_dcf(
    costs: CostInputs, dcf: DcfInputs, assumptions, *, steady_deliveries: float, scenario: Scenario
) -> DcfResult: ...
def run_dcf_views(
    costs: CostInputs,
    assumptions,
    *,
    steady_deliveries: float,
    scenario: Scenario,
    dcf: DcfInputs | None = None,
) -> DcfViews: ...
def npv(rate: float, cash_flows: Sequence[float]) -> float: ...
def irr(cash_flows: Sequence[float]) -> float | None: ...
def payback_years(cash_flows: Sequence[float], rate: float = 0.0) -> float | None: ...


# geo/catchment.py  (M3.5a, ADR-0004; replaces catchment_features(geo, radius_miles))
def catchment_features(
    geo: GeoContext,
    centers: Sequence[CenterSite],  # existing delivery centers: id, name, lat, lon
    demand: Sequence[ZipDemand],  # ZIPs: zip, lat, lon, deliveries_per_year
    beta: float = 2.0,
    *,
    radius_miles: float | None = None,
) -> CatchmentFeatures: ...


# geo/folium_map.py
def render_customer_map(
    geo: GeoContext, scored_features: "GeoDataFrame", out_path: Path
) -> Path: ...


# geo/resolve.py
def resolve_zip(zip_code: str) -> GeoContext: ...


# data/registry.py
def staleness_status(
    as_of: date | None, ttl_days: int, today: date
) -> Literal["fresh", "aging", "stale", "missing"]: ...


# storage/repository.py
def get_source(conn, source_id: str) -> SourceRecord | None: ...
def upsert_source(conn, record: SourceRecord) -> None: ...


# extract/pdf_llm.py  (optional; never imported by model or scenarios)
def extract_tariff_json(pdf_path: Path, cache: Path) -> dict[str, object]: ...
```

## Model clarifications (M3)

- **Assumptions.** Defaults ship in `data/defaults/assumptions.yaml` (`schema_version` for shape, `assumptions_version` for values). The model never reads the file: the caller loads it and passes the mapping. Model functions accept the raw `Assumptions` mapping or a parsed `ModelAssumptions`. Parsing is strict; unknown or missing keys raise.
- **Units.** `opex_load` is a fraction (0.15 = +15%). `wage_load` is a multiplier (1.30 = +30%) and must be ≥ 1. `demand_rate_kw` is USD per kW per month; the model multiplies by 12.
- **Shocks.** `wage_shock` scales labor only, `rent_shock` lease only. `delivery_shock` is applied by `apply_delivery_shock`, not inside `estimate_annual_deliveries`, so that contract signature stays scenario-free. `vehicle_mix` does not enter M3 math (M4). Every shock must be > −1.
- **Other OpEx.** `build_cost_inputs` sets `other_opex_annual` to a percentage of baseline (unshocked) lease + labor, so scenario shocks do not move it.
- **Drivers.** Ties rank by name ascending. Shares of the returned list sum to ≤ 1.0 under plain float addition.
- **Errors** (`dce.model.errors`, all `ValueError`): `ModelError` ← `InvalidInputError` ← {`AssumptionsError`, `ZeroDeliveriesError`}. `cost_per_delivery` raises `ZeroDeliveriesError` for deliveries ≤ 0.
- **Schema 3.** `schema_version: 3` is the only version accepted. Schema 2's shape still applies, plus `demand.handover_factor` and `demand.fallback_tesla_ev_share`. Any number may be a plain value or `{low, base, high}` with `low <= base <= high` by input value. Typed fields hold `base`. Every range is also in `ModelAssumptions.ranges`, keyed by dotted path (for example `"dcf.discount_rate"`), for the M4 scenarios and tornado. Vector ranges (`dcf.volume.ramp`, `seasonality.month_in_quarter`) carry their own low/base/high tuples. Sections from schema 2: `vehicle_mix` (sums to 1), `seasonality` (quarter shares and month-in-quarter splits, each sums to 1), `labor.wage_mix` (SOC entries, shares sum to 1), and `dcf`. `capex` splits into `fitout_psf`, `soft_contingency`, and `equipment_usd`. `property_tax.included_in_nnn: true` sets the property-tax component to 0 because the NNN `opex_load` already carries it.
- **Handover factor.** `demand.handover_factor` is 1.00 / 1.10 / 1.30 (low / base / high). Base 1.10 is what `estimate` applies to every ZIP after the county Tesla anchor. 1.10 and 1.30 are assumptions: no public source counts used-car handovers. `demand.fallback_tesla_ev_share` is 0.462, Cox/KBB 2025 Tesla share of US EV sales, used when a non-California caller has EV registrations and no Tesla make split. A California county with no CEC Tesla row keeps 49,704 / 94,131 instead of that national share.
- **Horizon.** `dcf.horizon_years` is 8 / 10 / 10. The high case is the 10-year lease. The decision scenarios do not assume a renewal.

## Catchment (M3.5a, ADR-0004)

Built in `dce.geo.catchment`. The orchestrator loads centers and ZIP demand and passes them in. Not part of `dce.model`.

- `centers` are `CenterSite` rows (id, name, lat, lon) for existing Tesla delivery centers. `estimate` passes every `location_type: delivery` row in the US snapshot (120 on 2026-11-08). The North San Jose hub and the possible-handover rows stay out; they are not on the Find Us delivery list. `demand` is `ZipDemand` (zip, lat, lon, Tesla handovers a year). A ZIP with a missing centroid or missing deliveries is skipped.
- Distance is straight-line between ZCTA internal points × 1.25 circuity, capped at 60 miles. Candidate share is `P_cz = d_cz^-β / Σ_k d_kz^-β` over the candidate plus all centers, with equal attractiveness. The default is β = 2; the nearest-center split is the low case.
- The return is `CatchmentFeatures`, not a GeoDataFrame. It holds `gravity` (base) and `nearest` (low). Each `CatchmentCase` has `zips` (zip, deliveries, share, straight-line miles, drive miles), `total_deliveries_per_year`, and `taken_from` (center id, name, deliveries). `EstimateResult.catchment` carries the same facts as `CatchmentSummary` (zips, deliveries per year, volume taken from each center) so the model package does not import geo.
- The steady-state deliveries that feed the cost model and `run_dcf` are `gravity.total_deliveries_per_year` after the county anchor and the base handover factor.
- California ZIP demand is `BEV_z × (CEC Tesla_county / Σ BEV in the county) × handover_factor`. Counties with no CEC Tesla row in the extract keep 49,704 / 94,131. The handover factor is 1.00 / 1.10 / 1.30; `estimate` uses 1.10.
- `radius_miles` is a straight-line fallback used only when `centers` is empty. `demand.base_annual_deliveries` is the calibration fallback only when ZIP-level EV data is missing.
- No network and no SQL in the geo module.
- On the raw extract (BEV × 49,704 / 94,131) and the nine Bay Area research centers, San Mateo 94402 is still 4,370 nearest-center deliveries and 5,523 gravity deliveries. The research text says gravity is about 5,720. That gap is not the 60-mile cap, the Gazetteer centroid, or rounding the Tesla share. `estimate` does not use that series. It uses the nationwide 2026 CEC seed, annualized from three quarters, handover 1.10, and the US delivery list. See `docs/STATUS.md` for the current 94402 figures.

## DCF (M3.5b, ADR-0005)

`dce.model.dcf` is pure. The full formulas are in its module docstring.

- `DcfInputs` (frozen) holds every knob: horizon, ramp, growth, capacity cap multiple, `benefit_mode` (`"standalone" | "incremental" | "gp_allocation"`), fee, freight, GP per vehicle, uplift, constraint share, status-quo rent, overtime multiplier, peak-excess share, fit-out, soft/contingency, equipment, pre-opening months, escalations, `wacc`, tax rates and lives, and `terminal` (`"none" | "renewal"`) with `terminal_g`. `build_dcf_inputs` fills it from the base values.
- `DcfYear` (frozen) is one table row. Its fields are `year`, `deliveries`, `headcount`, `benefit`, `lease`, `labor`, `utilities`, `property_tax`, `other_opex`, `opex`, `ebitda`, `capex`, `fed_depreciation`, `state_depreciation`, `tax`, `fcf`, `discounted_fcf`, `cumulative_fcf`, and `cumulative_discounted_fcf`. Year 0 is capex plus pre-opening labor.
- `DcfResult` (frozen) holds `benefit_mode`, `discount_rate`, `years`, `npv`, `irr` (`None` without a sign change), `simple_payback_years`, `discounted_payback_years` (`None` if never), `total_capex`, and `terminal_value`. `DcfViews` holds `standalone` (headline) and `incremental` (check).
- `run_dcf` takes `steady_deliveries` as a number (from the catchment or the demand fallback) instead of `geo`/`demand`, so it stays independent of the geo stack. `scenario.delivery_shock` scales it, `wage_shock` scales labor, and `rent_shock` scales lease, the same as the static model.
- **Reuse, not duplication.** Each operating year calls `annualized_components` on a copy of `CostInputs` with escalated rent, wage, and utility rates, that year's `staffing_headcount`, and other opex recomputed. `capex_total` is 0 in that copy. Upfront capex (`upfront_capex`) is explicit year-0 cash. With `ramp[0] == 1`, year-1 opex equals the static annualized total minus `capex`.
- Zero deliveries is valid input. The site still pays rent and the minimum crew, so NPV is negative, and IRR and paybacks are `None`.

## Rent resolver

```python
# data/ingest/*.py — fetch_* returns a frozen dataclass and does not open SQLite.

# data/rent_resolver.py
# Reads SQLite/seed only. No network. No LoopNet/Crexi.
def resolve_rent(zip_code: str, conn: sqlite3.Connection) -> RentResolution: ...
```

Fallback chain, first hit wins: observed CBSA industrial seed, unadjusted, then county GSA (ACS factor only when that CBSA has no seed), state and national industrial seeds, HUD SAFMR, this ZCTA's ACS gross rent, then the county, CBSA, state, and national median of ACS gross rent. Every rung after the observed seed is a fallback.

`RentResolution` carries `rent_psf_year`, `rent_psf_month`, `property_type`, `tier`, `confidence`, `as_of`, and `citation`. ZIP → CBSA is the HUD crosswalk.

## Orchestrator

```python
def estimate(
    zip_code: str,
    scenario: Scenario | None = None,
    overrides: Mapping[str, object] | None = None,
    *,
    data_dir: Path | None = None,
) -> EstimateResult: ...
```

Resolves the ZIP, loads that ZIP's ACS fields, rent, and OEWS wage through `load_zip_local`, and builds origin demand for the whole crosswalk. California demand is the 2026 CEC ZIP battery-electric count times the county Tesla share, times 4/3 because the file is three quarters, times handover 1.10. Other states share the Cox/KBB 2025 US Tesla total minus the 2025 CEC California Tesla total, weighted by households and income. The gravity catchment runs against the US delivery list (nearest-center is the low case). Gravity deliveries feed the cost model and `run_dcf_views`. A ZIP whose 60-mile catchment has no deliveries gets an isolated origin: the non-California deliveries per reference household times a household proxy (ACS households, else population divided by the national persons per household, else one household). That volume is not taken from any other ZIP. With no scenario argument, the result is the base outcome (explicit base fee, WACC, and horizon, and no price or volume shock). `provenance` records each input. `overrides` may include `rent_psf_month`. Electricity is the utility tariff (PG&E Schedule B-10 on PG&E territory), then the EIA-861 utility average, then the state price, then the U.S. price. An EIA average sets the demand charge to 0. Commercial property tax shifts the NNN load. Fit-out uses the BEA goods price parity. The building stays 25,000 square feet. No network. Never imports `extract.pdf_llm`.

`dce.precompute.precompute` calls `dce.app.results.build_ui_result` for each ZIP, stores the dashboard fields as zlib JSON, and vacuums the file. `get_zip_result` / `get_zip_results` read it. See `docs/contracts/precompute_results.md`.

## GUI and CLI

The desktop map is pywebview plus MapLibre in `dce.app` (ADR-0006). It reads a `dce.ui_result.v1` document. CLI lives in `dce.cli`. `dce estimate` calls `orchestrator.estimate`. `dce precompute` calls `dce.precompute.precompute` and does not open SQLite itself. The calculate path must not import `extract.pdf_llm`. There is no LLM call on this path.
