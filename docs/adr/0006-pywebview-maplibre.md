# ADR-0006: pywebview window and a local MapLibre map

- Status: accepted
- Date: 2026-11-09
- Supersedes: the shell in [ADR-0001](0001-tkinter-browser-map.md)

## Context

Jacob replaced the Tkinter form on 2026-11-09. The map is the app: a dark,
minimal basemap, ZIP boundaries, and the existing delivery centers, with the
estimate beside the map. A Folium file opened in the system browser cannot
host that dashboard, and PySide6 / Qt WebEngine stays out (ADR-0001's size
and notarization reasons still hold).

The primary artifact is still an unsigned macOS Apple Silicon `.app`
(ADR-0002). The page has to feel immediate, work when the tile server is
down, and ship without a CDN.

## Decision

The shell is a [pywebview](https://pywebview.flowrl.com/) window. On macOS
that is WKWebView, the system web view, not an embedded Chromium or Qt.

The page is local HTML, CSS, and JS under `src/dce/app/web/`. MapLibre GL JS
4.7.1 is vendored in that directory (BSD-3-Clause). The dark style file is
local. Its vector tiles and glyphs come from OpenFreeMap (OpenStreetMap
data) at runtime. If those requests fail, the page keeps the ZIP polygons
and the center markers on a flat dark background.

`window.pywebview.api` is the bridge (`dce.app.api.AppApi`):

- `bootstrap()` returns the ZCTA FeatureCollection, center markers, and the
  style path.
- `get_result(zip)` returns one dashboard document. A precomputed document
  wins when one exists. Otherwise the ZIP is computed on a worker thread,
  cached in memory, and optionally written under the user data directory.
  The page draws a skeleton until the call returns. A second click does not
  compute again.
- `compare(zip_a, zip_b)` returns both documents and which value is better.

The document shape is `docs/contracts/ui_results.md` (`dce.ui_result.v1`).

Polygons load from `data/geo/zcta_bay_area.geojson`, or from
`DCE_ZCTA_GEOJSON`. When `data/geo/zcta_us.pmtiles` is present (the
gitignored archive from `make zcta-boundaries`, layer `zcta`, zooms 3–8),
the page draws that nationwide set through the vendored PMTiles protocol.
Charts are SVG drawn by the page. No chart library and no CDN script.

`make app` opens the window. `make build` still runs `scripts/build_macos.sh`,
which runs PyInstaller only on macOS arm64. CI does not build the app.

## Consequences

- `import dce.app` must not import pywebview, so headless CI does not need
  a display or the GTK webview libraries.
- Do not add Tkinter or PySide6 to the shell.
- `dce.geo.folium_map` is no longer how the GUI shows a map.
- The frozen app bundles `dce/app/web`, `data/seed`, `data/defaults`,
  `data/demo`, and `data/geo/zcta_bay_area.geojson`. It also bundles
  `data/geo/zcta_us.pmtiles` when that file is present at build time.
  `dce.config.bundle_root` and `dce.geo.resolve._fixture_path` read
  `sys._MEIPASS` so a packaged app finds the seed without `pyproject.toml`
  beside the code.
- Precomputed rows are read from `DCE_UI_RESULTS_PATH` or from
  `get_zip_result` / `get_zip_results` through `dce.app.precomputed`.
  This package does not open SQLite and does not create a results table.
- Gatekeeper is unchanged: right-click the `.app` and choose Open the first
  time.
- A Windows EXE stays optional and later (ADR-0002).
