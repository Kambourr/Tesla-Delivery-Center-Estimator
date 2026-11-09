# Milestones (agent-sized)

Each milestone is sized for one coding agent. Acceptance is binary.

Decisions locked on 2026-11-09 (see PLAN and ARCHITECTURE): Tkinter, macOS Apple Silicon `.app` as the primary artifact, zero required inputs with automatic rent, bundled SQLite seed, LLM only in `dce.extract.pdf_llm`.

**Revised scope (Jacob, 2026-11-08).** A candidate ZIP returns a gravity catchment net of existing Tesla delivery centers (deliveries a year and the volume taken from each center), `$/delivery` with the top 3 drivers, scenarios, a map, and a 10-year DCF (NPV, IRR, simple and discounted payback, yearly cash-flow table) showing both the standalone and the incremental benefit views. Out of scope: Tesla internal data, home delivery, service repair, and multi-site optimization. Two milestones, M3.5a and M3.5b, sit between M3 and M4; later numbers are unchanged. Research: `docs/research/`. Decisions: ADR-0004, ADR-0005.

## M0 — Repo bootstrap (no product logic)
**Deliver:** Skeleton matching `REPO_STRUCTURE.md`; layered `src/dce` stubs with typed signatures; `pyproject.toml` as the config for pinned deps, ruff, mypy, and pytest-cov; pre-commit; Makefile; `CONTRIBUTING.md`; ADRs 0001–0003; `data/seed/README.md`; CI on `macos-latest` and `ubuntu-latest` that lints, typechecks, and tests. No secrets.
**Accept:** `pip install -e .` works; `python -m dce --help` prints the stub CLI and exits 0; `pytest` passes; `ruff` and `mypy` pass; the workflow file is valid YAML and does not reference secrets. No network calls from package code.

## M1 — SQLite schema + config + ZIP resolve stub
**Deliver:** `storage/schema.sql`, `storage/migrate.py`, `storage/repository.py`, `config.py` paths (`~/Library/Application Support/DeliveryCenterEstimator` on macOS, `%LOCALAPPDATA%\DeliveryCenterEstimator` on Windows, `~/.local/share/delivery-center-estimator` on Linux), `geo/resolve.py` using a local HUD sample fixture for 9440x.
**Accept:** Creating the DB is idempotent; a unit test inserts and reads `source_registry`; resolving `94402` returns county `06081` and a CBSA from the fixture. No network.

## M2 — Public loaders (Census ACS ZCTA, OEWS metro, CA EV ZIP)
**Deliver:** `census_acs.py`, `bls_oews.py`, `ca_ev.py` with allowlisted fetch + SQLite upsert + `as_of`. Demo seed script for San Mateo without requiring all keys in CI (fixtures).
**Accept:** An integration test (optional network) or a fixture test loads ACS population + income for 94402, OEWS 49-3023 for the San Francisco–Oakland metro (or a fixture), and CEC/DMV EV counts for 94402. Staleness helper is unit-tested.

## M3 — Deterministic cost + demand model + top-3 drivers
**Deliver:** Pure `demand.py`, `costs.py`, `drivers.py` per `MODULE_CONTRACTS.md`; assumptions YAML; unit tests with fixed fixtures (no network). Rent dollars arrive as an input; this milestone does not resolve rent.
**Accept:** Given frozen inputs, `$/delivery` matches golden JSON to 2 decimals; top-3 shares sum to at most 1.0; zero deliveries raises a clean error.

## M3.5a — Gravity catchment net of existing centers (ADR-0004)
**Deliver:** A seed table of existing US Tesla delivery centers from the public Find Us delivery list (`as_of`, source URL, staleness TTL). ZCTA Tesla demand (CA: CEC ZIP BEV sales × Tesla share of BEV; elsewhere the `dce.model.demand` allocator). `catchment_features(geo, centers, demand, beta)` in `dce.geo.catchment` with a Huff split (β = 2, equal attractiveness, straight-line × 1.25 circuity, 60-mile cap) and a nearest-center low case. Code lives in `src/dce/geo/` and `src/dce/data/ingest/`; the model stays pure.
**Accept:** For 94402 with the demo seed, deliveries handled are within the research band (about 4,400 nearest-center to 5,700 Huff β = 2 a year). The volume taken from each existing center is reported, and it sums to the deliveries handled to within 1 delivery a year. Each per-ZCTA candidate share is in [0, 1]. `radius_miles` is used only when no center list is given. No network in tests.

## M3.5b — 10-year DCF with two benefit views (ADR-0005)
**Deliver:** Pure `dce.model.dcf` (`DcfInputs`, `DcfYear`, `DcfResult`, `DcfViews`, `run_dcf`, `run_dcf_views`, `npv`, `irr`, `payback_years`). Schema-2 `assumptions.yaml` with researched low / base / high values and a `dcf:` block. Capex moves to explicit year-0 cash in the DCF. `EstimateResult.dcf: DcfViews | None = None`.
**Accept:** San Mateo golden, standalone: NPV @13.6% = +$9.7M ± $0.1M, IRR 66% ± 1 pt, simple payback 1.7 ± 0.05 yr, discounted payback 2.0 ± 0.05 yr, and the research cash-flow rows to within $1k. Incremental (75% constrained, 1% uplift): NPV −$2.8M ± $0.25M with no payback. Year-1 opex with no ramp equals the static annualized total minus `capex`. Zero deliveries and fee-below-freight never pay back (IRR and paybacks `None`). `make check` is green.

## M4 — Scenarios (±20% wage, vehicle mix, DCF shocks) + robustness
**Deliver:** `scenarios/grid.py`, `scenarios/robustness.py`; CLI `estimate --scenario-grid`. `Scenario` gains optional `discount_rate_shock`, `growth_shock`, and `benefit_mode`. `expand_default_scenarios` adds WACC low/high (9.7% / 16.3%) and growth 0% / 10%. `dcf_tornado(base_inputs, ranges)` returns `(driver, npv_low, npv_high)` sorted by swing, using the `ModelAssumptions.ranges` low/high values. Driver-rank Spearman also ranks NPV drivers. Default vehicle mix comes from `assumptions.vehicle_mix`.
**Accept:** Grid emits baseline + wage±20% + alternate mix + WACC low/high + growth 0/10%; Spearman driver-rank vs baseline is in [−1, 1]; a test proves wage+20% does not change lease dollars. The San Mateo standalone tornado ranks deliveries first, and every bar brackets the base NPV.

## M5 — Map (gravity catchment + Folium HTML)
**Deliver:** Demo GeoPackage for San Mateo ZCTAs; `geo/folium_map.py` rendering the M3.5a catchment: core polygon where `P_cz ≥ 0.5`, other ZCTAs shaded by `P_cz`, a candidate marker, and markers for existing centers labeled with the volume taken from each. HTML is a file the GUI will open in the system browser. Offline note in the README (polygons must not depend on a live tile server).
**Accept:** `94402` writes HTML with at least one polygon layer, a candidate marker, and at least one existing-center marker; a test checks the file exists and contains a Folium / GeoJSON snippet.

## M6 — Rent fallback, crosswalks, and rates (still no scraping)
**Deliver:** Bundled rent seed (CBSA industrial asking rents cited to public CBRE / Cushman / Colliers / JLL reports), HUD ZIP→CBSA fixture or seed, frozen ACS rent-model coefficients, GSA calibration notes, `resolve_rent` fallback chain (ZIP-adjusted CBSA → county → CBSA → state → national → HUD SAFMR/ZORI proxy flagged low-confidence). EIA/OpenEI loaders. PG&E manual extract JSON for B-10/B-19 cached. Optional advanced rent override is not required for the accept path.
**Accept:** Estimating a ZIP uses resolved rent when no override is present and shows tier, confidence, `as_of`, and citation. No LoopNet/Crexi code path exists (search gate in CI). First-launch path reads the bundled seed and does not require network.

## M7 — Tkinter GUI + macOS PyInstaller .app
**Deliver:** Tkinter form (ZIP, scenario presets, Refresh data, Run, staleness and rent-confidence badges, Open map via the system browser). Results show `$/delivery` with the top 3 drivers, catchment deliveries and the volume taken from each center, and the DCF: standalone NPV / IRR / paybacks as the headline, the incremental lens beside it, the yearly cash-flow table (CSV export), and the cumulative-FCF payback chart. Optional advanced rent override may be present and must not be required. `packaging/dce_macos.spec` and `scripts/build_macos.sh` produce an arm64 `.app` that bundles `data/seed`. A Windows EXE is out of this milestone.
**Accept:** On Apple Silicon the `.app` builds; a headless smoke launch exits 0; offline first launch from the bundled seed works for 94401–94404. Document right-click → Open for Gatekeeper.

## M8 — Polish / handoff
**Deliver:** README quickstart brought current, STATUS update, sample screenshots (optional), OPEN_QUESTIONS resolved or parked.
**Accept:** A new agent can follow the README to the golden path without chat history.
