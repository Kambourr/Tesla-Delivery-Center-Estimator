# Agent Handoff — scope revised; M3.5a catchment and M3.5b DCF

M0–M3 are merged. Jacob revised the scope on 2026-11-08 (PLAN "Revised scope", ADR-0004, ADR-0005, research in `docs/research/`). Two milestones now sit before M4:

- **M3.5a, gravity catchment** (`src/dce/geo/`, `src/dce/data/ingest/`). This is being built separately. Follow the `catchment_features(geo, centers, demand, beta)` contract in `MODULE_CONTRACTS.md`.
- **M3.5b, DCF** (`src/dce/model/dcf.py`). This is the `claude/dcf-scope` pull request: schema-2 `assumptions.yaml` with researched low / base / high values and a `dcf:` block, `EstimateResult.dcf`, and San Mateo goldens.

Read `docs/STATUS.md` before writing code. Do not merge unless Jacob asks.

The M2 notes below are the record of that milestone. Do not rebuild them.

## Locked decisions

- Public data only. No Tesla internal files. No LoopNet, Crexi, CoStar, or other listing scrapes. No paid CRE API.
- GUI is a **pywebview** window and a local **MapLibre** page (ADR-0006). Do not add Tkinter or PySide6. Basemap tiles may load at runtime. ZIP polygons are local (`data/geo`).
- Primary artifact is a **macOS Apple Silicon `.app`**. Windows is optional and later.
- The only required input is a US ZIP. Rent resolves automatically (DATA_SOURCES §8). An optional advanced override is allowed and must not be required.
- Bundled SQLite seed; offline on first launch; per-source staleness flags.
- Deterministic math. The only module that may call an LLM is `dce.extract.pdf_llm`. Do not import it from `dce.model`, `dce.orchestrator`, or the GUI calculate path.
- Secrets live in `.env` only. CI has no secrets. `.env.example` names are `CENSUS_API_KEY`, `BLS_API_KEY`, `EIA_API_KEY`, `HUD_TOKEN`.
- OEWS for 94401–94404 uses parent CBSA `41860`, not HUD division `41884`. `GeoContext.cbsa` stays `41884`.
- Staleness is computed by `staleness_status`. It is not a column. Fresh is the first half of `ttl_days`, aging is the rest, stale is past the TTL, missing means no `as_of`. Eighteen months is 548 days.

## Read first

- `docs/PLAN.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULE_CONTRACTS.md`
- `docs/REPO_STRUCTURE.md`
- `docs/MILESTONES.md` (M3 acceptance)
- `docs/DATA_DICTIONARY.md`
- `docs/OPEN_QUESTIONS.md` (do not reopen locked items)

## M2 record (done)

1. `fetch_zcta_acs`, `fetch_oews_wage`, and `fetch_ev_zip` hit only allowlisted hosts and return frozen dataclasses. They do not open SQLite.
2. `dce.data.persist` upserts `zcta_acs`, `oews_wage`, `ev_zip`, and `source_registry` (`as_of`, `fetched_at`, `ttl_days`). The Census key never goes in the stored URL.
3. `data/demo/san_mateo` plus `scripts/fetch_demo_cache.py` load 94402 (and 94401, 94403, 94404) with no keys. CI tests that path. Live calls are opt-in via `DCE_NETWORK_TESTS=1`.
4. `staleness_status` is unit-tested. `scripts/check_staleness.py` reports it.
5. Schema version 2 adds `median_home_value`. Do not edit the version-1 statements.

## Out of scope for M2

Cost and demand math, scenario grid, rent resolution, PyInstaller on a Mac, the CEC bulk workbook, and the remaining ingest stubs. The map window is ADR-0006.

## Done when M3 starts

M3 is pure `demand.py`, `costs.py`, and `drivers.py` per `MODULE_CONTRACTS.md`, with assumptions YAML and golden tests. Rent dollars arrive as an input. Do not resolve rent in M3. No network.
