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

Until the national ZCTA extract lands, polygons load from
`DCE_ZCTA_GEOJSON` or, by default, the Bay Area fixture shipped in
`src/dce/app/web/fixtures/`. Charts are SVG drawn by the page. No chart
library and no CDN script.

`make app` opens the window. `make build` still runs `scripts/build_macos.sh`,
which runs PyInstaller only on macOS arm64. CI does not build the app.

## Consequences

- `import dce.app` must not import pywebview, so headless CI does not need
  a display or the GTK webview libraries.
- Do not add Tkinter or PySide6 to the shell.
- `dce.geo.folium_map` is no longer how the GUI shows a map.
- The frozen app bundles `dce/app/web`, `data/seed`, `data/defaults`,
  `data/demo`, and the HUD fixture. `dce.config._project_root` and
  `dce.geo.resolve._fixture_path` still walk parents for `pyproject.toml`
  and do not yet understand PyInstaller's `_MEIPASS`. A `.app` built from
  the spec will not resolve 94402 until that lookup is taught. See the PR
  that introduced this ADR.
- Precomputed rows are read from `DCE_UI_RESULTS_PATH` or, when storage adds
  it, `dce.storage.repository.get_ui_result(zip_code) -> str | dict | None`.
  This package does not open SQLite.
- Gatekeeper is unchanged: right-click the `.app` and choose Open the first
  time.
- A Windows EXE stays optional and later (ADR-0002).
