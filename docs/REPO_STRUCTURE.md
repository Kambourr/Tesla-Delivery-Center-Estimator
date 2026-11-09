# Repository Structure

M0 matches this tree. Package directories include `__init__.py`. Modules are
stubs: typed signatures, frozen dataclasses, and docstrings. No product logic.

Naming and layer rules: [CONTRIBUTING.md](../CONTRIBUTING.md).
Decisions: [docs/adr](adr/README.md).

```
delivery-center-estimator/
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE                        # placeholder; license not chosen
├── Makefile                       # setup, lint, typecheck, test, build
├── pyproject.toml                 # deps plus ruff, mypy, pytest, coverage
├── .pre-commit-config.yaml
├── .env.example                   # CENSUS_API_KEY, BLS_API_KEY, EIA_API_KEY, HUD_TOKEN
├── .gitignore
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
│   ├── OPEN_QUESTIONS.md
│   ├── research/                  # public-data research behind the defaults (2026-11-08)
│   │   ├── tesla_delivery_ops_research.md
│   │   └── dcf_design.md
│   └── adr/
│       ├── 0001-tkinter-browser-map.md
│       ├── 0002-macos-pyinstaller.md
│       ├── 0003-rent-fallback-no-scraping.md
│       ├── 0004-gravity-catchment.md
│       └── 0005-dcf-dual-benefit-views.md
├── src/
│   └── dce/
│       ├── __init__.py
│       ├── __main__.py            # python -m dce
│       ├── config.py
│       ├── orchestrator.py        # composition root: estimate(zip)
│       ├── cli/
│       │   └── main.py
│       ├── app/
│       │   └── main.py            # Tkinter. M0 does not import tkinter.
│       ├── data/
│       │   ├── registry.py        # staleness. Pure given as_of and today.
│       │   ├── rent_defaults.py   # read curated seed; no scrapers
│       │   ├── rent_resolver.py
│       │   └── ingest/            # fetch_* only
│       │       ├── census_acs.py
│       │       ├── census_geo.py
│       │       ├── bls_oews.py
│       │       ├── bls_qcew.py
│       │       ├── hud_crosswalk.py
│       │       ├── ca_ev.py
│       │       ├── eia_rates.py
│       │       └── openei_urdb.py
│       ├── storage/
│       │   ├── schema.sql
│       │   ├── connection.py
│       │   ├── migrate.py
│       │   └── repository.py      # the only SQL
│       ├── model/                 # pure calc
│       │   ├── types.py
│       │   ├── demand.py
│       │   ├── costs.py
│       │   ├── drivers.py
│       │   └── dcf.py             # 10-year DCF, NPV/IRR/payback
│       ├── scenarios/
│       │   ├── grid.py
│       │   └── robustness.py
│       ├── geo/
│       │   ├── resolve.py
│       │   ├── catchment.py
│       │   └── folium_map.py
│       └── extract/
│           ├── hashing.py
│           ├── pdf_manual.py
│           └── pdf_llm.py         # only LLM module
├── data/
│   ├── demo/
│   ├── defaults/
│   └── seed/                      # README: provenance and licensing
├── tests/
│   ├── unit/                      # mirrors src/dce layers
│   ├── integration/
│   └── fixtures/
├── scripts/
│   ├── refresh_public_data.py
│   ├── fetch_demo_cache.py
│   ├── check_staleness.py
│   ├── build_macos.sh
│   └── build_windows.ps1
├── packaging/
│   ├── dce_macos.spec
│   └── dce.spec
└── .github/
    ├── CODEOWNERS
    └── workflows/ci.yml           # lint, typecheck, tests; no secrets
```

## Packaging

- Primary build host is macOS Apple Silicon. Spec: `packaging/dce_macos.spec`. Script: `scripts/build_macos.sh`. Target `arm64`.
- Windows EXE is optional and must be built on Windows.
- Bundle `data/seed` so first launch works offline.
- User database: `~/Library/Application Support/DeliveryCenterEstimator/` on Mac; `%LOCALAPPDATA%\DeliveryCenterEstimator\` on Windows; `~/.local/share/delivery-center-estimator/` on Linux.
- M0 specs exit with a stub message. `make build` calls the macOS script and exits 1.

## CI

`.github/workflows/ci.yml` installs Python 3.12 and the `dev` extra, then runs ruff, mypy, pytest, and `python -m dce --help` on `macos-latest` and `ubuntu-latest`. No secrets. No packaging job.

## What never goes in the tree

- API keys, scraped LoopNet/Crexi HTML, the full national TIGER zip, verbatim teardown PDFs, Tesla internal CSVs.
- Paid CRE extracts (CoStar, CompStak, Reonomy, ATTOM, Cherre).
- A real `LICENSE` body before one is chosen.
