# Tesla Delivery-Center Cost Estimator — Product Plan

**Owner:** Jacob Kambour (SCU MS Finance & Analytics; Tesla Sales & Delivery Advisor, Bay Area)  
**Product:** macOS desktop `.app` (Apple Silicon) answering: *What if Tesla opens a delivery center in ZIP code X?* A Windows EXE is an optional later target.  
**Stack:** Python · pandas · geopandas · Folium · Tkinter · SQLite · PyInstaller (macOS arm64)  
**Constraint:** PUBLIC DATA ONLY. Never Tesla internal data, never scrape ToS-prohibited sites into the calc path.

## Goal

Given any US ZIP code, produce outputs that work offline on first launch (bundled seed):

1. **Estimated cost per delivery** ($/delivery) for a hypothetical delivery center at that ZIP.
2. **Top three cost drivers** (share of total annualized cost, with labels).
3. **Customer-base map** (Folium HTML, opened in the system browser) coloring nearby block groups / ZCTAs by an EV-demand proxy score.

Demo focus: San Mateo, CA — `94401`, `94402`, `94403`, `94404`.

## Locked decisions (Jacob, 2026-11-09)

1. **GUI is Tkinter.** The Folium map HTML opens in the system browser. PySide6 is not the v1 UI.
2. **Primary artifact is a macOS Apple Silicon `.app`** built with PyInstaller. Windows EXE is optional and later. CI runs tests on `macos-latest` (and may also run them on `ubuntu-latest`). No secrets in CI.
3. **Zero required manual input.** Typing a US ZIP resolves every input, including rent. Rent is a bundled curated metro industrial asking-rent seed (public CBRE / Cushman / Colliers / JLL market reports, with citations). ZIP maps to CBSA via the HUD crosswalk, then a frozen ACS income / density / home-value model (calibrated with the GSA Lease Inventory) adjusts it. Fallback chain: ZIP-adjusted CBSA → county → CBSA → state → national → HUD SAFMR/ZORI proxy flagged low-confidence. Never scrape LoopNet or Crexi. Rent override is not a required input. An optional advanced override is allowed.
4. **Bundled seed data in SQLite** so the app works offline even on first launch. Each source has its own refresh cadence and a staleness flag.
5. **Deterministic core math.** An LLM API is allowed only in `dce.extract.pdf_llm`, never on the calculation path.

## Scope

| In | Out |
|---|---|
| Any US ZIP → ZCTA / county / CBSA join | Tesla internal volume, mix, lease, or wage data |
| Annualized cost model + $/delivery | Live web hosting / SaaS |
| Scenario presets: vehicle mix + ±20% wage swings | Automated LoopNet/Crexi scraping |
| Robustness: rank correlation of drivers/ZIPs across scenarios | Claiming official Tesla site-selection authority |
| Bundled SQLite seed (offline on first launch) plus optional refresh | Windows EXE as the primary artifact |
| Staleness flags per source in the UI | LLM anywhere in the cost math path |
| Tkinter shell; Folium HTML in the system browser | PySide6 / embedded web engine |
| Optional advanced rent override | Rent as a required input |

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
| **Lease / occupancy** | `rent_psf_yr × sqft × (1 + opex_load)` | `resolve_rent(zip)`: bundled CBSA industrial asking rent, HUD ZIP→CBSA, frozen ACS adjustment calibrated on GSA leases, then the fallback chain. Optional advanced override only. **Never scrape LoopNet/Crexi.** |
| **Labor** | Headcount × loaded wage × FTE | BLS OEWS metro mean for SOC **49-3023** (Automotive Service Technicians and Mechanics) + related delivery/admin SOCs; QCEW county NAICS for auto-dealer / repair as cross-check / scaler |
| **Utilities** | kWh × $/kWh + demand charges (simplified) | PG&E published commercial schedules (demo); EIA retail commercial $/kWh by state; OpenEI URDB as structured fallback |
| **Property tax** | Assessed value × effective rate (county default) | County assessor public rates / defaults table |
| **Capex amortization** | Capex ÷ useful life (straight-line) | Assumption defaults + optional teardown-derived fit-out / equipment unit costs (**fair-use excerpts only; no verbatim copyrighted teardowns in repo**) |
| **Other OpEx** | Insurance, IT, supplies as % of labor+lease | Configurable % assumptions table |

### Estimated annual deliveries (demand proxy)

Composite score at ZIP / surrounding catchment (radius or drive-time proxy via ZCTA neighbors):

```
deliveries ≈ base_throughput × f(income, ev_stock, population, commute)
```

Factors (public):

- ACS 5-year ZCTA / block-group: population, median household income, vehicles available, commute mode/time.
- CA: CEC / DMV light-duty ZEV counts by ZIP (demo). Other states: DOE AFDC / state DMV open data where available; else ACS EV-ownership proxies + national EV share fallback with staleness flag.
- Catchment = center ZIP + neighboring ZCTAs within N miles (geopandas distance on ZCTA centroids) or HUD crosswalk → tracts → block groups.

`base_throughput` and elasticity weights are **Jacob-tunable assumptions** (open decision), not Tesla secrets.

### Top-3 cost drivers

1. Compute each component's dollar contribution to `annualized_total_cost`.
2. Rank descending; take top 3.
3. Report share = `component / annualized_total_cost`.
4. Under scenarios, recompute; surface Spearman rank correlation of (a) driver ranks and (b) ZIP $/delivery ranks vs baseline — **robustness check**.

### Scenario modeling

| Scenario knobs | Values |
|---|---|
| Vehicle mix | Preset mix table (e.g., Model 3/Y/S/X/Cybertruck shares) affecting labor minutes & energy |
| Wage swing | Baseline, −20%, +20% on labor unit costs |
| Optional | Rent ±20%, deliveries ±20% (shocks on resolved values, not typed rent) |

Core math is **deterministic** (pure Python / pandas). No LLM in this path.

### Map design

- Folium choropleth of block groups (preferred) or ZCTAs in catchment.
- Fill = normalized demand proxy (0–100).
- Marker at candidate ZIP centroid; legend. The Tkinter shell opens the HTML file in the system browser (`webbrowser.open`). Do not embed a web engine.
- Offline tiles: prefer embedded simplified geometry and no external tile URLs so polygons render offline. A tile basemap may be blank offline if one is added later — document that. A small San Mateo MBTiles file is an open question, not a requirement.
- Export path: `outputs/maps/{zip}_{timestamp}.html`.

## Assumptions table (defaults — tunable, not typed each run)

| ID | Assumption | Default | Source class |
|---|---|---|---|
| A1 | Delivery-center footprint | 25,000 SF | Industry warehouse proxy |
| A2 | Industrial rent | Resolved, not typed. Demo seed should land near published Bay Area industrial headlines (~$1.50–$1.65 /SF/mo, annualized) | Public CBRE/Cushman/Colliers/JLL snapshots, cited in the seed |
| A3 | Opex load on rent | 15% | Configurable |
| A4 | Tech headcount | f(deliveries) with floor | Configurable staffing curve |
| A5 | Wage load (benefits/taxes) | 1.30× | Configurable |
| A6 | Capex | $80–$150 /SF fit-out (placeholder) | Public broker/build cost proxies; teardown-inspired unit costs only as optional advanced assumptions |
| A7 | Capex life | 10 years | Configurable |
| A8 | Catchment radius | 15 miles | Configurable |
| A9 | Base annual deliveries @ median score | 2,500 | **Open decision** |
| A10 | Demo ZIPs | 94401–94404 | Product brief |

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

- macOS `.app` opens, accepts `94402`, returns $/delivery, top-3 drivers, and opens the map HTML in the system browser.
- Works offline on first launch from the bundled seed.
- Scenario ±20% wage + mix change updates results; rank-correlation metric shown.
- README + docs make a later agent able to pick up any module.
