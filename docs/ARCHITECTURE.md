# Architecture

## Platforms

| Priority | Artifact | Build host |
|---|---|---|
| **Primary** | macOS `.app` (Apple Silicon `arm64`; optional `universal2` later) | Tests on `macos-latest`. The `.app` is built on Apple Silicon (PyInstaller cannot cross-compile this stack). |
| Secondary | Windows EXE | `windows-latest` only if a Windows artifact is requested |

Unsigned student Mac apps: document **right-click → Open** the first time (Gatekeeper). Codesign and notarization are out of scope for the class project.

**CI (M0):** GitHub Actions on `macos-latest` and `ubuntu-latest`. Steps: install the package, ruff, mypy, `pytest`, `python -m dce --help`. **No secrets.** The workflow does not run PyInstaller. Tool config lives in `pyproject.toml`. See `docs/adr/0002-macos-pyinstaller.md`.

## Zero manual input

Orchestrator `estimate(zip_code)` loads **all** inputs from the bundled seed and the user SQLite database (rent via `resolve_rent(zip)`, wages, EV, rates, defaults). The GUI and CLI accept **only a US ZIP**, plus optional scenario preset buttons.

An **optional advanced rent override** may be offered later for a sensitivity check. It is never required. The default path resolves rent with no typing beyond the ZIP.

## Runtime shape

```
[dce.app pywebview + MapLibre | dce.cli]
        │
        ▼
   dce.orchestrator.estimate(zip)
        │
        ├─► dce.storage          SQLite only
        ├─► dce.data.ingest      fetch_* (refresh only)
        ├─► dce.data             rent resolver + staleness
        ├─► dce.model            pure calc, no I/O
        ├─► dce.scenarios        grid on top of the model, no I/O
        ├─► dce.geo              catchment geometry (no browser)
        └─► dce.extract          optional PDF→JSON; never on the calc path
```

## GUI decision

**pywebview + a local MapLibre page.** ADR-0006. This replaces the Tkinter form and the Folium file opened in the system browser.

The window is the OS web view (WKWebView on macOS), not Qt and not an embedded Chromium. The page, MapLibre GL JS, and the PMTiles protocol are files in the app. Basemap tiles may load from OpenFreeMap at runtime. ZIP polygons are local: `data/geo/zcta_bay_area.geojson`, and `data/geo/zcta_us.pmtiles` when `make zcta-boundaries` has built it. Do not add PySide6 or Tkinter. `import dce.app` does not import pywebview, so headless CI does not need a display.

## Layers

1. **App / CLI** (`dce.app`, `dce.cli`) — the map window takes a ZIP. The page calls `estimate(zip)` through the pywebview bridge. ADR-0006. The CLI is the headless entry.
2. **Orchestrator** — `estimate(zip, scenario=None, overrides=None) -> EstimateResult`. The only composition root.
3. **Storage** — connection, migrations, repository. The only SQL.
4. **Ingest** — `fetch_*` for allowlisted hosts. Returns dataclasses. No SQL.
5. **Rent resolver** (`dce.data.rent_resolver`) — fallback chain in DATA_SOURCES §8 and ADR-0003. Reads SQLite only.
6. **Model** — demand, costs, drivers, and the 10-year DCF (`dce.model.dcf`, ADR-0005). No I/O, no network, no LLM.
7. **Scenarios** — mix, wage, discount-rate, and growth grid; Spearman checks; NPV tornado. Calls the model. No I/O.
8. **Geo** — gravity catchment net of existing delivery centers (ADR-0004) and ZIP resolution. The map the user sees is MapLibre in `dce.app`, not Folium HTML.
9. **Extract** — optional PDF extraction. `pdf_llm` is the only module that may call an LLM. Nothing in `model/`, `scenarios/`, or the calculate path may import it.

## Determinism

Same seed/SQLite + ZIP + scenario ⇒ identical floats. The LLM never feeds the model live.

## Offline and seed

- Ship `data/seed/` inside the app. First launch copies seed into the user database and works with **no network**.
- Refresh is explicit and per source. Each source has a cadence and a staleness flag: `fresh` | `aging` | `stale` | `missing`.
- User database:
  - macOS: `~/Library/Application Support/DeliveryCenterEstimator/dce.sqlite`
  - Windows: `%LOCALAPPDATA%\DeliveryCenterEstimator\dce.sqlite`
  - Linux (dev): `~/.local/share/delivery-center-estimator/dce.sqlite`

## Packaging

- macOS (primary): `packaging/dce_macos.spec`, `scripts/build_macos.sh`, target `arm64`.
- Windows (optional, later): `packaging/dce.spec`, `scripts/build_windows.ps1`. Build on Windows only.
- Bundle `data/seed/` so first launch works offline.
- `scripts/build_macos.sh` runs PyInstaller only on macOS arm64. `dce.config.bundle_root` reads `sys._MEIPASS` so the frozen app finds `data/seed` and `data/geo`. CI does not build the `.app`.

## Rent resolution (locked)

See DATA_SOURCES §8.

```
ZIP-adjusted CBSA industrial
  → county
  → raw CBSA
  → state
  → national
  → HUD SAFMR / ZORI proxy (confidence low)
```

Seed rents are curated headline asking rents from public CBRE, Cushman, Colliers, and JLL market reports, with citations. ZIP→CBSA is the HUD crosswalk. The ZIP adjustment is a frozen ACS model (income, density, home value) calibrated with the GSA Lease Inventory. No LoopNet, Crexi, or paid CRE API.
