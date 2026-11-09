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
class EstimateResult:
    geo: GeoContext
    scenario: Scenario
    cost_per_delivery: float
    annualized_total_cost: float
    estimated_annual_deliveries: float
    components: dict[str, float]
    drivers: list[Driver]
    map_path: str | None
    dcf: DcfViews | None = None  # M3.5b; standalone + incremental lenses (ADR-0005)
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
    centers: "GeoDataFrame",  # existing delivery centers: center_id, name, zcta, geometry (point)
    demand: "GeoDataFrame",  # ZCTAs: zcta, tesla_deliveries_per_year, geometry
    beta: float = 2.0,
) -> "GeoDataFrame": ...


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
- **Schema 2 (M3.5b).** `schema_version: 2` is the only version accepted. Any number may be a plain value or `{low, base, high}` with `low <= base <= high` by input value. Typed fields hold `base`. Every range is also in `ModelAssumptions.ranges`, keyed by dotted path (for example `"dcf.discount_rate"`), for the M4 scenarios and tornado. Vector ranges (`dcf.volume.ramp`, `seasonality.month_in_quarter`) carry their own low/base/high tuples. New sections: `vehicle_mix` (sums to 1), `seasonality` (quarter shares and month-in-quarter splits, each sums to 1), `labor.wage_mix` (SOC entries, shares sum to 1), and `dcf`. `capex` splits into `fitout_psf`, `soft_contingency`, and `equipment_usd`. `property_tax.included_in_nnn: true` sets the property-tax component to 0 because the NNN `opex_load` already carries it.

## Catchment (M3.5a, ADR-0004)

Built in `dce.geo.catchment` and `dce.data.ingest`. Not part of `dce.model`.

- `centers` are existing Tesla delivery centers from the seed (public Find Us list snapshot with `as_of`). `demand` holds Tesla deliveries a year per ZCTA.
- Distance is straight-line between ZCTA internal points × 1.25 circuity, capped at 60 miles. Candidate share is `P_cz = d_cz^-β / Σ_k d_kz^-β` over the candidate plus all centers, with equal attractiveness. The default is β = 2; the nearest-center split is the low case.
- The returned frame has one row per ZCTA. Its columns are `zcta`, `geometry`, `tesla_deliveries_per_year`, `candidate_share` (in [0, 1]), `candidate_deliveries` (`D_z · P_cz`), and `taken_from_<center_id>` (`D_z · (P⁰_kz − P_kz)`). The candidate's annual deliveries are `candidate_deliveries.sum()`. They feed `steady_deliveries` for the DCF and the `$/delivery` denominator.
- `facility.catchment_miles` is the fallback only when `centers` is empty. `demand.base_annual_deliveries` is the fallback only when ZIP-level EV data is missing.
- No network and no SQL in the geo module. The caller passes frames that storage has already loaded.

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

Fallback chain, first hit wins: ZIP-adjusted CBSA industrial (broker seed × frozen ACS income/density/home-value model, calibrated on the GSA Lease Inventory) → county → raw CBSA → state → national → HUD SAFMR or ZORI proxy with confidence `low`.

`RentResolution` carries `rent_psf_year`, `rent_psf_month`, `property_type`, `tier`, `confidence`, `as_of`, and `citation`. ZIP → CBSA is the HUD crosswalk.

## Orchestrator

```python
def estimate(
    zip_code: str, scenario: Scenario | None = None, overrides: Mapping[str, object] | None = None
) -> EstimateResult: ...
```

Loads from the bundled seed and SQLite (optional refresh if missing/stale and online), resolves rent, calls the model, optionally writes a map. `overrides` may include an optional advanced rent override. ZIP alone must succeed. Never imports `extract.pdf_llm`.

## GUI and CLI

Tkinter in `dce.app`. Required field is the ZIP. "Open map" uses `webbrowser.open` on the Folium HTML file. No PySide6 and no embedded web engine. The calculate path must not import `extract.pdf_llm`. CLI lives in `dce.cli` and calls `orchestrator.estimate`.
