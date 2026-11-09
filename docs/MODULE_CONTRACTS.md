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
def build_cost_inputs(assumptions, *, rent_psf_month, wage_annual, energy_rate_kwh,
                      demand_rate_kw, annual_deliveries) -> CostInputs: ...

# scenarios/grid.py
def expand_default_scenarios(base_mix: dict[str, float]) -> list[Scenario]: ...
def run_scenario_grid(geo, demand, costs, scenarios, assumptions) -> list[EstimateResult]: ...

# scenarios/robustness.py
def spearman_rank_corr(ranks_a: list[str], ranks_b: list[str]) -> float: ...
def driver_rank_stability(results: list[EstimateResult], baseline_id: str) -> dict[str, float]: ...

# geo/folium_map.py
def render_customer_map(geo: GeoContext, scored_features: "GeoDataFrame", out_path: Path) -> Path: ...

# geo/resolve.py
def resolve_zip(zip_code: str) -> GeoContext: ...

# data/registry.py
def staleness_status(as_of: date | None, ttl_days: int, today: date) -> Literal["fresh","aging","stale","missing"]: ...

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
def estimate(zip_code: str, scenario: Scenario | None = None, overrides: Mapping[str, object] | None = None) -> EstimateResult: ...
```

Loads from the bundled seed and SQLite (optional refresh if missing/stale and online), resolves rent, calls the model, optionally writes a map. `overrides` may include an optional advanced rent override. ZIP alone must succeed. Never imports `extract.pdf_llm`.

## GUI and CLI

Tkinter in `dce.app`. Required field is the ZIP. "Open map" uses `webbrowser.open` on the Folium HTML file. No PySide6 and no embedded web engine. The calculate path must not import `extract.pdf_llm`. CLI lives in `dce.cli` and calls `orchestrator.estimate`.
