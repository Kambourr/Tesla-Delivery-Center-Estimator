# Tesla Delivery-Center Cost Estimator — Product Plan

**Owner:** Jacob Kambour (SCU MS Finance & Analytics; Tesla Sales & Delivery Advisor, Bay Area)\
**Product:** macOS desktop `.app` (Apple Silicon) answering: *What if Tesla opens a delivery center in ZIP code X?* A Windows EXE is an optional later target.\
**Stack:** Python · pandas · geopandas · MapLibre (local) · pywebview · SQLite · PyInstaller (macOS arm64)\
**Constraint:** PUBLIC DATA ONLY. Never Tesla internal data, never scrape ToS-prohibited sites into the calc path.

## Goal

Given any US candidate ZIP code, produce outputs that work offline on first launch (bundled seed):

1. **Catchment net of existing Tesla delivery centers.** A Huff gravity model (distance exponent β = 2) over nearby ZCTAs gives deliveries a year for the candidate and the volume taken from each existing center (ADR-0004).
2. **Estimated cost per delivery** ($/delivery) for a hypothetical delivery center at that ZIP.
3. **Top three cost drivers** (share of total annualized cost, with labels).
4. **Scenarios** (wage, vehicle mix, rent, deliveries, discount rate, growth) with a robustness check and an NPV tornado.
5. **Map** (MapLibre in the pywebview window, ADR-0006) shading ZCTAs by the candidate's gravity share, with markers for the existing centers.
6. **10-year DCF.** NPV, IRR, simple and discounted payback, and a yearly cash-flow table, under two benefit views shown together (ADR-0005):
   - **Standalone** delivery-fee contribution (the headline).
   - **Incremental to Tesla**: capacity-constraint share, avoided overtime, and proximity uplift (the check).

   Default discount rate is Tesla's WACC, 13.6% (low 9.7%, high 16.3%).

Demo focus: San Mateo, CA — `94401`, `94402`, `94403`, `94404`.

## Revised scope (Jacob, 2026-11-08)

The goal above replaces the original three outputs ($/delivery, top-3 drivers, demand-score map). It adds the gravity catchment (ADR-0004) and the DCF with two benefit views (ADR-0005). Out of scope: Tesla internal data, home delivery (Carrier Direct), service repair, and multi-site optimization. The research behind the defaults is in `docs/research/` (public data only, 2026-11-08).

## Locked decisions (Jacob, 2026-11-09)

1. **GUI is a pywebview window and a local MapLibre page** (ADR-0006, 2026-11-09). This supersedes Tkinter and a Folium file in the system browser. PySide6 is not the UI.
2. **Primary artifact is a macOS Apple Silicon `.app`** built with PyInstaller. Windows EXE is optional and later. CI runs tests on `macos-latest` (and may also run them on `ubuntu-latest`). No secrets in CI.
3. **Zero required manual input.** Typing a US ZIP resolves every input, including rent. Rent is a bundled curated metro industrial asking-rent seed (public CBRE / Cushman / Colliers / JLL market reports, with citations). ZIP maps to CBSA via the HUD crosswalk, then a frozen ACS income / density / home-value model (calibrated with the GSA Lease Inventory) adjusts it. Fallback chain: ZIP-adjusted CBSA → county → CBSA → state → national → HUD SAFMR/ZORI proxy flagged low-confidence. Never scrape LoopNet or Crexi. Rent override is not a required input. An optional advanced override is allowed.
4. **Bundled seed data in SQLite** so the app works offline even on first launch. Each source has its own refresh cadence and a staleness flag.
5. **Deterministic core math.** An LLM API is allowed only in `dce.extract.pdf_llm`, never on the calculation path.

## Scope

| In | Out |
|---|---|
| Any US ZIP → ZCTA / county / CBSA join | Tesla internal volume, mix, lease, or wage data |
| Gravity catchment net of existing delivery centers | Home delivery (Carrier Direct) |
| Annualized cost model + $/delivery | Service and repair operations |
| 10-year DCF: NPV, IRR, paybacks, standalone + incremental views | Multi-site network optimization |
| Scenario presets: vehicle mix, ±20% wage, WACC, growth; NPV tornado | Live web hosting / SaaS |
| Robustness: rank correlation of drivers/ZIPs across scenarios | Automated LoopNet/Crexi scraping |
| Bundled SQLite seed (offline on first launch) plus optional refresh | Claiming official Tesla site-selection authority |
| Staleness flags per source in the UI | Windows EXE as the primary artifact |
| pywebview window; local MapLibre page (ADR-0006) | LLM anywhere in the cost math path |
| Optional advanced rent override | PySide6 / embedded web engine; rent as a required input |

## Non-goals

- Not a production Tesla planning tool; portfolio / practicum FP&A demo.
- Not real-time utility billing or site acquisition workflow.
- Not multi-user sync; single local SQLite DB.

## Cost model design

### Identity

```
cost_per_delivery = annualized_total_cost / estimated_annual_deliveries
```

### Annualized total cost (sum of components)

| Component | Method | Primary public input |
|---|---|---|
| **Lease / occupancy** | `rent_psf_yr × sqft × (1 + opex_load)`. Rent is NNN, so `opex_load` carries the landlord's property tax | `resolve_rent(zip)`: bundled CBSA industrial asking rent, HUD ZIP→CBSA, frozen ACS adjustment calibrated on GSA leases, then the fallback chain. Optional advanced override only. **Never scrape LoopNet/Crexi.** |
| **Labor** | Headcount × loaded wage × FTE | BLS OEWS metro means blended by the delivery-role mix in `labor.wage_mix`: 41-2031 retail salespersons (Tesla Advisor) 45%, 53-7061 vehicle cleaners 30%, 53-7062/53-7065 yard and stock 15%, 41-1011 supervisors 10%. 49-3023 is service-center staff and is no longer the default. QCEW as a cross-check |
| **Utilities** | kWh × $/kWh + demand charges (simplified) | PG&E published commercial schedules (demo); EIA retail commercial $/kWh by state; OpenEI URDB as structured fallback |
| **Property tax** | Assessed value × effective rate (county default); 0 when `property_tax.included_in_nnn` (the default) | County assessor public rates / defaults table |
| **Capex amortization** | (fit-out × sqft × (1 + soft/contingency) + equipment) ÷ life, straight-line. The DCF spends the same capex as year-0 cash instead | Assumption defaults + optional teardown-derived fit-out / equipment unit costs (**fair-use excerpts only; no verbatim copyrighted teardowns in repo**) |
| **Other OpEx** | Insurance, IT, supplies as % of labor+lease | Configurable % assumptions table |

### Estimated annual deliveries (gravity catchment)

Per ADR-0004 and `docs/research/tesla_delivery_ops_research.md` §6:

1. **Demand per ZCTA** (Tesla deliveries a year). California: CEC ZIP-level BEV sales × Tesla share of BEV, trailing four quarters. Other states: state Tesla volume allocated to ZCTAs with the existing elasticity form (`dce.model.demand`).
2. **Supply points**: existing US delivery centers from Tesla's public Find Us list, snapshotted with `as_of` and a staleness flag.
3. **Distance**: straight-line × 1.25 circuity, capped at 60 miles.
4. **Allocation**: candidate share `P_cz = d_cz^-β / Σ_k d_kz^-β`, β = 2 (sensitivity 1.5–3). Nearest-center is the low case.
5. **Outputs**: deliveries handled `Σ_z D_z · P_cz` and the volume taken from each existing center. For San Mateo 94402 the research gives about 4,400 (nearest-center) to 5,700 (β = 2) a year, mostly from Colma and Sunnyvale.

`demand.base_annual_deliveries` (low 3,000 / base 4,500 / high 6,500) is a calibration fallback used only when ZIP-level EV data is missing. A fixed radius (`facility.catchment_miles`) is used only when no center list is available. Elasticity weights and references are **Jacob-tunable assumptions**, not Tesla secrets.

### Top-3 cost drivers

1. Compute each component's dollar contribution to `annualized_total_cost`.
2. Rank descending; take top 3.
3. Report share = `component / annualized_total_cost`.
4. Under scenarios, recompute; surface Spearman rank correlation of (a) driver ranks and (b) ZIP $/delivery ranks vs baseline — **robustness check**.

### Scenario modeling

| Scenario knobs | Values |
|---|---|
| Vehicle mix | Default Model Y 0.70 / Model 3 0.27 / Cybertruck 0.03 / S, X 0 (`assumptions.vehicle_mix`) |
| Wage swing | Baseline, −20%, +20% on labor unit costs |
| Discount rate | Tesla WACC 13.6%; low 9.7%, high 16.3% |
| Volume growth after ramp | 0% / 5% / 10% a year |
| Optional | Rent ±20%, deliveries ±20% (shocks on resolved values, not typed rent) |
| NPV tornado | Every input with a low/high range in `assumptions.yaml` (deliveries, fee, freight, deliveries per FTE, WACC, growth, fit-out, wage, rent) |

Core math is **deterministic** (pure Python / pandas). No LLM in this path.

### DCF design

See ADR-0005 and `docs/research/dcf_design.md`. Pure `dce.model.dcf`, end-of-year cash flows, 10-year horizon (the lease term). Year 0 is capex plus three months of pre-opening labor.

- **Volume**: catchment steady state × ramp (75% / 95% / 100% in years 1–3), then 5% growth a year, capped at 1.5× steady state.
- **Opex**: the cost model each year, with rent +3.5%, wages +3.1%, and utilities +3% a year. Capex is year-0 cash, not an annual charge.
- **Standalone benefit (headline)**: deliveries × ($1,390 destination fee − $150 inbound freight).
- **Incremental benefit (check)**: `constraint_share` (0.75) × (status-quo expansion opex + fit-out annuity), plus the overtime premium avoided on peak-month volume, plus 1% uplift × deliveries × $7,233 gross profit per vehicle.
- **Tax**: federal 21% with 100% bonus in year 0; California 8.84% with 39-year / 7-year straight line and a lease-end write-off.
- **Terminal value**: none by default; renewal perpetuity optional.
- **Outputs**: NPV at 13.6%, IRR, simple and discounted payback, the yearly cash-flow table, and the cumulative-FCF payback chart.

Illustrative San Mateo base (research estimate): standalone NPV about +$9.7M, IRR about 66%, payback 1.7 / 2.0 years; incremental about −$2.8M. That gap is the decision question: the site pays for itself as a delivery business but adds value for Tesla only if the existing centers are capacity-bound.

### Map design

- MapLibre fill of ZCTAs in the gravity catchment. The selected ZIP is highlighted, and other ZCTAs in the catchment are shaded by share.
- Markers at existing delivery centers. The page is the pywebview window (ADR-0006). Do not add Tkinter or PySide6.
- Offline tiles: prefer embedded simplified geometry and no external tile URLs so polygons render offline. A tile basemap may be blank offline if one is added later — document that. A small San Mateo MBTiles file is an open question, not a requirement.
- Export path: `outputs/maps/{zip}_{timestamp}.html`.

## Assumptions table (defaults — tunable, not typed each run)

Values live in `data/defaults/assumptions.yaml` (schema 2), with low / base / high where the research gives a range. Sources are in `docs/research/`.

| ID | Assumption | Default (low / base / high) | Source class |
|---|---|---|---|
| A1 | Delivery-center footprint | 13,000 / 25,000 / 60,000 SF | Colma and Port Coquitlam sites; base is a placeholder |
| A2 | Industrial rent | Resolved, not typed. San Mateo research case $2.14 /SF/mo NNN | Public broker reports, cited in the seed |
| A3 | Opex load on rent | 15% (covers the landlord's property tax) | Configurable |
| A4 | Staffing | `max(min_headcount, deliveries / deliveries_per_fte)`; minimum 6 / 10 / 15, 200 / 300 / 450 deliveries per FTE | ASSUMPTION build-up (research §5) |
| A5 | Wage load (benefits/taxes) | 1.30 / 1.35 / 1.43× | BLS ECEC Jun 2026 |
| A6 | Capex | Fit-out $60 / $100 / $160 /SF hard + 20% soft/contingency; equipment $0.5M / $0.78M / $1.2M | RLB, terrapincg, charger cost surveys |
| A7 | Capex life | 10 years (lease term) | Configurable |
| A8 | Catchment | Gravity model, β = 2 (ADR-0004); radius fallback 10 / 15 / 35 miles | Research §6 |
| A9 | Base annual deliveries (fallback) | 3,000 / 4,500 / 6,500 | US 4,364 per center (2025), CA 5,473 |
| A10 | Demo ZIPs | 94401–94404 | Product brief |
| A11 | Seasonality | Quarters 23 / 26 / 28 / 23%; month in quarter 25 / 30 / 45% (base) | CEC CA 2024–25; ASSUMPTION for months |
| A12 | Discount rate | 9.7% / 13.6% / 16.3% (Tesla WACC) | CAPM, Damodaran ERP, UST 10y |
| A13 | DCF benefit inputs | Fee $1,250 / $1,390 / $1,640; freight $75 / $150 / $343; constraint share 0.5 / 0.75 / 1.0; uplift 0 / 1 / 3% | Edmunds, Transportli, ASSUMPTION |

## LLM isolation (optional)

- Module: `src/dce/extract/pdf_llm.py` only.
- Allowed: extract structured fields from messy utility/tariff PDFs into JSON.
- Must cache `(pdf_hash → json)` in SQLite; never call from `model/` or the GUI calc path.
- Default offline path: hand-coded PG&E schedule parsers + EIA/OpenEI numbers.

## Offline strategy

1. The app ships a bundled SQLite seed (`data/seed/`). First launch copies it into the user database and works with no network.
2. Optional "Refresh data" fetches allowlisted public sources and updates SQLite. Each source has its own cadence.
3. The UI shows per-source `as_of` and a staleness badge (`fresh` / `aging` / `stale` / `missing`).
4. An optional advanced rent override, if present, is stored only on the machine. It is never required.

## Success criteria (MVP)

- macOS `.app` opens and accepts `94402`. It returns catchment deliveries (with the volume taken from each existing center), $/delivery, the top-3 drivers, and the DCF: standalone NPV / IRR / paybacks with the incremental view beside it, plus the yearly cash-flow table. It opens the map HTML in the system browser.
- Works offline on first launch from the bundled seed.
- Scenario ±20% wage + mix change updates results; rank-correlation metric shown. WACC low/high and growth shocks move NPV, and the tornado is shown.
- README + docs make a later agent able to pick up any module.
