# Agent Handoff — M1 is in; next work is M2

M1 (SQLite schema, app-data paths, and local ZIP resolution) is implemented. Read `docs/STATUS.md` before writing code. Start **M2** from `main` after the M1 pull request merges. Do not merge unless Jacob asks.

The M1 notes below are the record of that milestone. Do not rebuild them.

## Locked decisions

- Public data only. No Tesla internal files. No LoopNet, Crexi, CoStar, or other listing scrapes. No paid CRE API.
- GUI is **Tkinter**. Folium HTML opens in the system browser. Do not add PySide6.
- Primary artifact is a **macOS Apple Silicon `.app`**. Windows is optional and later.
- The only required input is a US ZIP. Rent resolves automatically (DATA_SOURCES §8). An optional advanced override is allowed and must not be required.
- Bundled SQLite seed; offline on first launch; per-source staleness flags.
- Deterministic math. The only module that may call an LLM is `dce.extract.pdf_llm`. Do not import it from `dce.model`, `dce.orchestrator`, or the GUI calculate path.
- Secrets live in `.env` only. CI has no secrets. `.env.example` names are `CENSUS_API_KEY`, `BLS_API_KEY`, `EIA_API_KEY`, `HUD_TOKEN`.

## Read first

- `docs/PLAN.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULE_CONTRACTS.md`
- `docs/REPO_STRUCTURE.md`
- `docs/MILESTONES.md` (M1 acceptance)
- `docs/DATA_DICTIONARY.md`
- `docs/OPEN_QUESTIONS.md` (do not reopen locked items)

## M1 record (done)

1. Keep `src/dce` importable. `python -m dce --help` must keep working.
2. Implement `storage/schema.sql`, `storage/connection.py`, `storage/migrate.py`, and `storage/repository.py` for the DATA_DICTIONARY tables (at least `source_registry`, `zcta_acs`, `oews_wage`, `ev_zip`, `utility_rate`, `rent_default`, `extract_cache`). Creating the database is idempotent. SQL stays in `storage`.
3. The physical rent tables in DATA_SOURCES §8 (`rent_cbsa`, `rent_zip_obs`, `rent_model_coeffs`, `rent_resolved_cache`) belong to M6. Do not implement `resolve_rent` in M1.
4. `config.py`: macOS `~/Library/Application Support/DeliveryCenterEstimator`, Windows `%LOCALAPPDATA%\DeliveryCenterEstimator`, Linux `~/.local/share/delivery-center-estimator`.
5. Implement `geo/resolve.py`: `resolve_zip("94402")` using `tests/fixtures/hud_9440x.json` → `GeoContext` (county `06081` and a CBSA from the fixture). No network. Do not put this in the model.
6. Unit tests for migrate and resolve. Leave the M0 smoke test passing.
7. Update `docs/STATUS.md` when done.

## Out of scope for M1

Network loaders, Tkinter window, Folium output, PyInstaller, LLM, rent-resolver math, seed curation.

## Done when

Every M1 acceptance criterion in `docs/MILESTONES.md` passes locally, and `pytest` still passes with no network.
