# Repository Structure

Target: clean boundaries so any agent can land in one folder and ship a milestone.

M0 matches this tree. Package directories include `__init__.py` (not repeated below). Modules are stubs with docstrings that state the contract. There is no product logic yet.

```
delivery-center-estimator/
├── README.md
├── pyproject.toml                 # pinned runtime deps; pytest in the dev extra
├── .env.example                   # CENSUS_API_KEY, BLS_API_KEY, EIA_API_KEY, HUD_TOKEN
├── .gitignore                     # .env, caches, dist, build, generated sqlite
├── docs/
│   ├── PLAN.md
│   ├── DATA_SOURCES.md
│   ├── DATA_DICTIONARY.md
│   ├── ARCHITECTURE.md
│   ├── MODULE_CONTRACTS.md
│   ├── REPO_STRUCTURE.md
│   ├── MILESTONES.md
│   ├── AGENT_HANDOFF.md
│   ├── STATUS.md
│   └── OPEN_QUESTIONS.md
├── src/
│   └── dce/
│       ├── __init__.py
│       ├── __main__.py            # python -m dce
│       ├── cli.py                 # argparse stub
│       ├── config.py              # paths, TTLs, assumption file location
│       ├── orchestrator.py        # estimate(zip) → EstimateResult
│       ├── db/
│       │   ├── schema.sql         # comment placeholder until M1
│       │   ├── connection.py
│       │   └── migrate.py
│       ├── data/
│       │   ├── registry.py        # source_registry + staleness
│       │   ├── census_acs.py
│       │   ├── census_geo.py
│       │   ├── bls_oews.py
│       │   ├── bls_qcew.py
│       │   ├── hud_crosswalk.py
│       │   ├── ca_ev.py           # CEC / DMV
│       │   ├── eia_rates.py
│       │   ├── openei_urdb.py
│       │   ├── rent_defaults.py   # curated seed loader — no scrapers
│       │   └── rent_resolver.py   # ZIP fallback chain
│       ├── extract/
│       │   ├── pdf_manual.py      # regex/tables for known PG&E PDFs
│       │   └── pdf_llm.py         # OPTIONAL; isolated; never on the calc path
│       ├── model/
│       │   ├── types.py           # frozen dataclasses
│       │   ├── demand.py
│       │   ├── costs.py
│       │   ├── drivers.py
│       │   ├── scenarios.py
│       │   └── robustness.py
│       ├── map/
│       │   ├── catchment.py
│       │   └── folium_map.py      # HTML file; no embedded browser
│       ├── gui/
│       │   └── app.py             # Tkinter shell (stdlib). M0 does not import tkinter.
│       └── util/
│           ├── geo_zip.py
│           └── hashing.py
├── data/
│   ├── demo/                      # later: San Mateo GPKG + sample rows
│   ├── defaults/                  # later: assumptions.yaml
│   └── seed/                      # later: bundled SQLite seed (offline first launch)
├── tests/
│   ├── test_smoke.py              # M0: one passing test
│   ├── unit/
│   ├── integration/               # network tests, when added, must be optional
│   └── fixtures/
├── scripts/
│   ├── fetch_demo_cache.py        # stub; must not fetch in M0
│   ├── build_macos.sh             # stub; primary packaging entry
│   ├── build_windows.ps1          # stub; optional later EXE
│   └── check_staleness.py
├── packaging/
│   ├── dce_macos.spec             # stub; Apple Silicon .app
│   └── dce.spec                   # stub; optional Windows EXE
└── .github/workflows/
    └── ci.yml                     # macos-latest + ubuntu-latest; test only; no secrets
```

## Naming conventions

- Package import: `dce.*`
- Loaders: `fetch_*` (network, allowlisted hosts only) / `load_*` (SQLite) / `upsert_*`
- Model pure functions: no I/O; take dataclasses in, return dataclasses out
- Tests mirror package path once units exist: `tests/unit/model/test_costs.py`

## GUI

**Tkinter + system browser.** Decided for v1.

The map stays a file (`outputs/maps/…html`). The GUI opens that file with `webbrowser.open`. PySide6 is out of scope.

## PyInstaller

- **Primary build host is macOS Apple Silicon** (`macos-latest` or Jacob’s Mac). Spec: `packaging/dce_macos.spec`. Script: `scripts/build_macos.sh`. Target `arm64`.
- **Windows EXE is optional.** Building it on Linux or macOS is unsupported for this stack (geopandas / shapely wheels). Use `windows-latest` only when that artifact is requested.
- Bundle `data/seed` (and demo fixtures) as datas so first launch works offline.
- First-run user DB: `~/Library/Application Support/DeliveryCenterEstimator/` on Mac; `%LOCALAPPDATA%\DeliveryCenterEstimator\` on Windows; `~/.local/share/delivery-center-estimator/` on Linux.
- M0 does not run PyInstaller. The spec files exit with a stub message.

## CI

`.github/workflows/ci.yml` checks out the repo, installs Python 3.12, runs `pip install -e ".[dev]"`, `pytest`, and `python -m dce --help` on `macos-latest` and `ubuntu-latest`. No secrets. No packaging job.

## What never goes in the tree

- API keys, scraped LoopNet/Crexi HTML, the full national TIGER zip, verbatim teardown PDFs, Tesla internal CSVs.
- Paid CRE extracts (CoStar, CompStak, Reonomy, ATTOM, Cherre).
