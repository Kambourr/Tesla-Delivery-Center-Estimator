# Milestones (agent-sized)

Each milestone is sized for one coding agent. Acceptance is binary.

Decisions locked on 2026-11-09 (see PLAN and ARCHITECTURE): Tkinter, macOS Apple Silicon `.app` as the primary artifact, zero required inputs with automatic rent, bundled SQLite seed, LLM only in `dce.extract.pdf_llm`.

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

## M4 — Scenarios (±20% wage, vehicle mix) + robustness
**Deliver:** `scenarios/grid.py`, `scenarios/robustness.py`; CLI `estimate --scenario-grid`.
**Accept:** Grid emits baseline + wage±20% + alternate mix; Spearman driver-rank vs baseline is in [−1, 1]; a test proves wage+20% does not change lease dollars.

## M5 — Map (geopandas catchment + Folium HTML)
**Deliver:** Demo GeoPackage for San Mateo block groups / ZCTAs; `geo/catchment.py`, `geo/folium_map.py`. HTML is a file the GUI will open in the system browser. Offline note in the README (polygons must not depend on a live tile server).
**Accept:** `94402` writes HTML with at least one polygon layer and a center marker; a test checks the file exists and contains a Folium / GeoJSON snippet.

## M6 — Rent fallback, crosswalks, and rates (still no scraping)
**Deliver:** Bundled rent seed (CBSA industrial asking rents cited to public CBRE / Cushman / Colliers / JLL reports), HUD ZIP→CBSA fixture or seed, frozen ACS rent-model coefficients, GSA calibration notes, `resolve_rent` fallback chain (ZIP-adjusted CBSA → county → CBSA → state → national → HUD SAFMR/ZORI proxy flagged low-confidence). EIA/OpenEI loaders. PG&E manual extract JSON for B-10/B-19 cached. Optional advanced rent override is not required for the accept path.
**Accept:** Estimating a ZIP uses resolved rent when no override is present and shows tier, confidence, `as_of`, and citation. No LoopNet/Crexi code path exists (search gate in CI). First-launch path reads the bundled seed and does not require network.

## M7 — Tkinter GUI + macOS PyInstaller .app
**Deliver:** Tkinter form (ZIP, scenario presets, Refresh data, Run, staleness and rent-confidence badges, Open map via the system browser). Optional advanced rent override may be present and must not be required. `packaging/dce_macos.spec` and `scripts/build_macos.sh` produce an arm64 `.app` that bundles `data/seed`. A Windows EXE is out of this milestone.
**Accept:** On Apple Silicon the `.app` builds; a headless smoke launch exits 0; offline first launch from the bundled seed works for 94401–94404. Document right-click → Open for Gatekeeper.

## M8 — Polish / handoff
**Deliver:** README quickstart brought current, STATUS update, sample screenshots (optional), OPEN_QUESTIONS resolved or parked.
**Accept:** A new agent can follow the README to the golden path without chat history.
