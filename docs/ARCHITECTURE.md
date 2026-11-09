# Architecture

## Platforms

| Priority | Artifact | Build host |
|---|---|---|
| **Primary** | macOS `.app` (Apple Silicon `arm64`; optional `universal2` later) | Tests on `macos-latest`. The `.app` is built on Apple Silicon (PyInstaller cannot cross-compile this stack). |
| Secondary | Windows EXE | `windows-latest` only if a Windows artifact is requested |

Unsigned student Mac apps: document **right-click → Open** the first time (Gatekeeper). Codesign and notarization are out of scope for the class project.

**CI (M0):** GitHub Actions on `macos-latest`, plus an `ubuntu-latest` test job for the same suite. Steps: install the package, `pytest`, `python -m dce --help`. **No secrets.** The M0 workflow does not run PyInstaller.

## Zero manual input

Orchestrator `estimate(zip_code)` loads **all** inputs from the bundled seed and the user SQLite database (rent via `resolve_rent(zip)`, wages, EV, rates, defaults). The GUI and CLI accept **only a US ZIP**, plus optional scenario preset buttons.

An **optional advanced rent override** may be offered later for a sensitivity check. It is never required. The default path resolves rent with no typing beyond the ZIP.

## Runtime shape

```
[Tkinter GUI | CLI]
        │
        ▼
   Orchestrator estimate(zip)
        │
        ├─► Data layer (bundled seed + optional refresh → SQLite)
        ├─► Rent resolver (fallback chain; no required rent field)
        ├─► Model layer (pure; deterministic)
        ├─► Map layer → Folium HTML → system browser
        └─► Extract layer (optional PDF→JSON; isolated; never on the calc path)
```

## GUI decision

**Tkinter + the system browser.** This is the v1 decision.

| | **Tkinter (v1)** | **PySide6 (not v1)** |
|---|---|---|
| License | PSF (stdlib). Not a pip dependency. | LGPL v3 |
| PyInstaller size | Smaller | Larger (Qt, often 100MB+) |
| Folium map | `webbrowser.open(html_path)` | QWebEngine is fragile to notarize; do not use it |
| macOS Gatekeeper | Simpler unsigned path | Heavier signing surface |

Do not add PySide6. Do not embed a web engine. On Debian/Ubuntu, Tkinter's C module is the `python3-tk` package; M0 does not import Tkinter, so CI does not need it.

## Layers

1. **GUI / CLI** — ZIP entry only; scenario presets; staleness and rent-confidence badges; "Open map" launches the HTML file in the system browser.
2. **Orchestrator** — `estimate(zip, scenario=None, overrides=None) -> EstimateResult`.
3. **Rent resolver** — fallback chain in DATA_SOURCES §8; writes `rent_resolved_cache`. Reads SQLite only.
4. **Data** — bundled seed always present so first launch is offline; allowlisted HTTP only on explicit refresh; per-source `as_of` and staleness.
5. **Model** — demand, costs, drivers, scenarios, robustness. No I/O, no network, no LLM.
6. **Map** — catchment geometry → Folium HTML file → OS browser.
7. **Extract** — optional PDF extraction. `pdf_llm` is the only module that may call an LLM. Nothing in `model/` or the GUI calculate path may import it.

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
- M0 specs and build scripts are stubs. They do not invoke PyInstaller.

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
