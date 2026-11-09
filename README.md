# Tesla Delivery-Center Estimator

Desktop app that answers: **what if Tesla opens a delivery center in ZIP X?**

It will estimate cost per delivery, the top three cost drivers, and a customer-base map. It uses **public data only**. It never uses Tesla internal data, and it never scrapes LoopNet or Crexi.

**Status:** the desktop UI is a pywebview window with a local MapLibre map (ADR-0006). `estimate(zip)` is the calculation. CI still does not build the `.app`.

## Locked decisions

- **GUI:** a pywebview window (WKWebView on macOS) hosting a local MapLibre page. MapLibre GL JS and the PMTiles protocol are vendored. No CDN script. ADR-0006 supersedes the Tkinter and Folium-in-the-browser shell. PySide6 is not the UI.
- **Package:** macOS Apple Silicon `.app` via PyInstaller. A Windows EXE is an optional later target.
- **Input:** a US ZIP resolves rent and every other input. Rent is not a required field. An optional advanced override may be added later.
- **Data:** a bundled SQLite seed so the first launch works offline, plus a per-source refresh cadence and staleness flags.
- **Math:** deterministic. An LLM API is allowed only in `dce.extract.pdf_llm`, never on the calculation path.

The spec lives in [`docs/`](docs/). Layer rules and naming are in [`CONTRIBUTING.md`](CONTRIBUTING.md). Accepted decisions are in [`docs/adr/`](docs/adr/README.md).

## Quickstart

Requires Python 3.11 or newer.

```bash
make setup
source .venv/bin/activate
make check
python -m dce --help
```

`make check` runs ruff, mypy, and pytest. `make app` opens the map (it needs a display). `make zip-inputs` and `make zcta-boundaries` rebuild the public extracts; they are not part of CI. `pip install -e .` installs the package without the dev tools. Use `pip install -e ".[dev]"` if you are not using the Makefile.

Copy `.env.example` to `.env` only when you refresh Census, BLS, EIA, or HUD. The San Mateo demo does not need those keys:

```bash
python scripts/fetch_demo_cache.py --db /tmp/dce-demo/dce.sqlite
python scripts/check_staleness.py --db /tmp/dce-demo/dce.sqlite
```

That loads ACS population and income for 94401–94404, May 2025 OEWS SOC 49-3023 for the San Francisco–Oakland–Fremont metro (CBSA 41860), and DMV light-duty vehicle counts. `--refresh` calls the allowlisted hosts. Census refresh needs `CENSUS_API_KEY`. Tests do not use the network.

`python -m dce.app` opens the map. pywebview is imported only then, so headless `make check` does not need a display or GTK. ZIP polygons come from `data/geo/zcta_bay_area.geojson`. After `make zcta-boundaries`, `data/geo/zcta_us.pmtiles` (gitignored, layer `zcta`, zooms 3–8) covers the rest of the US. Tiles for the dark basemap load from OpenFreeMap at runtime and the page still draws ZIP boundaries when those requests fail.

`LICENSE` is a placeholder. A license has not been chosen.

## CI

GitHub Actions (`.github/workflows/ci.yml`) installs the package and runs lint, typecheck, and tests on `macos-latest` and `ubuntu-latest`. The workflow has no secrets and does not build the `.app`.

## Layout

See [`docs/REPO_STRUCTURE.md`](docs/REPO_STRUCTURE.md).
